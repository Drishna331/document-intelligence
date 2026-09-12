import re
from pydantic import ValidationError

from ..core.errors import AppError
from ..schemas.extraction import (
    WireDocument,
    ExtractedData,
    Value,
    Evidence,
    Period,
    Table,
    TableRow,
    LineItem,
    MINIMUM_FIELDS,
)
from ..utils.numbers import parse_number, infer_decimal_separator
from .prompts import build_prompt


def normalized_text(text):
    return ' '.join(text.split())


class ExtractionService:
    def __init__(self, client):
        self.client = client

    async def extract(self, document_type, pages):
        raw = await self.client.generate(
            build_prompt(document_type, pages)
        )

        # Only strip one enclosing JSON code fence.
        # No regex JSON reconstruction.
        fenced = re.fullmatch(
            r'\s*```(?:json)?\s*\n(.*)\n```\s*',
            raw,
            re.S,
        )

        if fenced:
            raw = fenced.group(1)

        try:
            wire = WireDocument.model_validate_json(raw)
            return self.ground(document_type, wire, pages)

        except ValidationError:
            raise AppError(
                'EXTRACTION_SCHEMA_ERROR',
                'The model output did not match the required extraction schema.',
                502,
            ) from None

    def ground(self, document_type, wire, pages):
        page_map = {
            p.page_number: p.text
            for p in pages
        }

        output = ExtractedData(
            tax_basis=wire.tax_basis,
            line_items_complete=wire.line_items_complete,
            warnings=list(wire.warnings),
        )

        periods = {}

        for p in wire.periods:
            if (
                not p
                or p in periods
                or not any(
                    normalized_text(p) in normalized_text(t)
                    for t in page_map.values()
                )
            ):
                raise AppError(
                    'INVALID_PERIODS',
                    'Reporting periods could not be matched uniquely to the source.',
                    502,
                )

            periods[p] = Period(
                period=p,
                fields={},
            )

        output.periods = list(periods.values())

        def value(content, kind):
            if content.raw_value is None:
                return Value(
                    reason='Not present or unreadable in the source.'
                )

            raw_value = content.raw_value
            page_text = page_map.get(content.page_number)
            quote = content.source_text
            reason = None

            # ---------------------------------------------------------
            # 1. Verify that the evidence exists on the claimed page.
            # ---------------------------------------------------------
            if (
                not page_text
                or not quote
                or normalized_text(quote)
                not in normalized_text(page_text)
            ):
                reason = (
                    'Evidence could not be found on the claimed source page.'
                )

            # ---------------------------------------------------------
            # 2. Verify that the extracted value occurs in the evidence.
            #
            # Numeric / percentage values:
            #   ALWAYS compared as numeric tokens, never as a raw
            #   substring check. Substring containment is unsound for
            #   numbers ("11" is a substring of "110.00"), so numeric
            #   fields must never rely on the text-substring branch.
            #
            #   If OCR has introduced a small non-numeric difference
            #   around the amount/currency/unit, compare the actual
            #   numeric token instead.
            #
            #   Example:
            #       OCR evidence: RN4.40
            #       Model value:  RM4.40
            #
            #   Both contain the independently verifiable numeric
            #   token 4.40, so this still matches.
            #
            # Text values:
            #   Require a case-insensitive direct substring match.
            # ---------------------------------------------------------
            elif kind in ('number', 'percentage'):
                raw_numeric = parse_number(
                    raw_value,
                    infer_decimal_separator(page_text),
                    percentage=kind == 'percentage',
                )

                quote_numbers = re.findall(
                    r'(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w.])',
                    normalized_text(quote),
                )

                numeric_match = False

                if raw_numeric is not None:
                    for candidate in quote_numbers:
                        candidate_numeric = parse_number(
                            candidate,
                            infer_decimal_separator(page_text),
                            percentage=kind == 'percentage',
                        )

                        if (
                            candidate_numeric is not None
                            and candidate_numeric == raw_numeric
                        ):
                            numeric_match = True
                            break

                if not numeric_match:
                    reason = (
                        'The reported raw value does not occur '
                        'in the evidence.'
                    )

            elif (
                normalized_text(raw_value).lower()
                not in normalized_text(quote).lower()
            ):
                reason = (
                    'The reported value does not occur in the evidence.'
                )

            # ---------------------------------------------------------
            # 3. Reject values that cannot be grounded.
            # ---------------------------------------------------------
            if reason:
                output.warnings.append(
                    'GROUNDING_REJECTED: ' + reason
                )

                return Value(
                    reason=reason
                )

            # ---------------------------------------------------------
            # 4. Preserve source evidence.
            # ---------------------------------------------------------
            evidence = Evidence(
                source_text=quote,
                page_number=content.page_number,
            )

            numeric = None

            # ---------------------------------------------------------
            # 5. Parse numeric values for financial validation.
            # ---------------------------------------------------------
            if kind in ('number', 'percentage'):
                numeric = parse_number(
                    raw_value,
                    infer_decimal_separator(page_text),
                    percentage=kind == 'percentage',
                )

                if numeric is None:
                    return Value(
                        value=None,
                        evidence=evidence,
                        reason=(
                            'The source amount is missing or '
                            'numerically ambiguous: ' + raw_value
                        ),
                    )

            return Value(
                value=raw_value,
                numeric_value=(
                    str(numeric)
                    if numeric is not None
                    else None
                ),
                evidence=evidence,
            )

        def assign(
            target,
            key,
            new,
            allow_same=False,
        ):
            if not re.fullmatch(
                r'[a-z][a-z0-9_]{0,99}',
                key,
            ):
                raise AppError(
                    'INVALID_FIELD_KEY',
                    'The model returned an invalid field identifier.',
                    502,
                )

            if key in target:
                if (
                    allow_same
                    and target[key].value == new.value
                ):
                    return

                raise AppError(
                    'CONFLICTING_VALUES',
                    'The model returned duplicate or conflicting '
                    'fields for a reporting period.',
                    502,
                )

            target[key] = new

        # -------------------------------------------------------------
        # Normal extracted fields
        # -------------------------------------------------------------
        for f in wire.fields:
            if (
                f.period is not None
                and f.period not in periods
            ):
                raise AppError(
                    'INVALID_PERIODS',
                    'An extracted field refers to an unknown period.',
                    502,
                )

            target = (
                periods[f.period].fields
                if f.period
                else output.fields
            )

            assign(
                target,
                f.key,
                value(
                    f.content,
                    f.kind,
                ),
            )

        # -------------------------------------------------------------
        # Tables
        # -------------------------------------------------------------
        for table in wire.tables:
            if len(set(table.columns)) != len(table.columns):
                raise AppError(
                    'DUPLICATE_COLUMNS',
                    'The model returned ambiguous table columns.',
                    502,
                )

            rows = []

            for row in table.rows:
                cells = {}

                for cell in row.cells:
                    if (
                        cell.column not in table.columns
                        or cell.column in cells
                    ):
                        raise AppError(
                            'INVALID_TABLE',
                            'The model returned an inconsistent table.',
                            502,
                        )

                    v = value(
                        cell.content,
                        cell.kind,
                    )

                    cells[cell.column] = v

                    if (
                        row.key
                        and cell.column in periods
                    ):
                        assign(
                            periods[cell.column].fields,
                            row.key,
                            v,
                            allow_same=True,
                        )

                for column in table.columns:
                    cells.setdefault(
                        column,
                        Value(
                            reason='Cell missing or unreadable.'
                        ),
                    )

                rows.append(
                    TableRow(
                        label=row.label,
                        key=row.key,
                        section=row.section,
                        role=row.role,
                        cells=cells,
                    )
                )

            output.tables.append(
                Table(
                    title=table.title,
                    columns=table.columns,
                    rows=rows,
                )
            )

        # -------------------------------------------------------------
        # Invoice line items
        # -------------------------------------------------------------
        for item in wire.line_items:
            fields = {}

            for f in item.fields:
                assign(
                    fields,
                    f.key,
                    value(
                        f.content,
                        f.kind,
                    ),
                )

            for key in [
                'description',
                'quantity',
                'unit_price',
                'line_total',
            ]:
                fields.setdefault(
                    key,
                    Value(
                        reason='Not present or unreadable in the source.'
                    ),
                )

            output.line_items.append(
                LineItem(
                    fields=fields,
                    amount_basis=item.amount_basis,
                )
            )

        # -------------------------------------------------------------
        # Reconciliations
        # -------------------------------------------------------------
        output.reconciliations = wire.reconciliations

        for g in wire.reconciliations:
            if (
                g.period not in periods
                or len(set(g.component_keys))
                != len(g.component_keys)
            ):
                raise AppError(
                    'INVALID_RECONCILIATION',
                    'The model returned an inconsistent component group.',
                    502,
                )

        # -------------------------------------------------------------
        # Ensure mandatory fields exist.
        # Missing fields become null/reason rather than invented values.
        # -------------------------------------------------------------
        required_targets = (
            [output.fields]
            if document_type == 'invoice'
            else [
                p.fields
                for p in output.periods
            ]
        )

        for target in required_targets:
            for key in MINIMUM_FIELDS[document_type]:
                target.setdefault(
                    key,
                    Value(
                        reason='Not present or unreadable in the source.'
                    ),
                )

        # -------------------------------------------------------------
        # Non-invoice documents must have reporting periods.
        # -------------------------------------------------------------
        if (
            document_type != 'invoice'
            and not periods
        ):
            raise AppError(
                'EXTRACTION_EMPTY',
                'No supported financial reporting periods were extracted.',
                422,
            )

        # -------------------------------------------------------------
        # Confirm that at least one grounded value exists.
        # -------------------------------------------------------------
        all_values = (
            list(output.fields.values())
            + [
                v
                for p in output.periods
                for v in p.fields.values()
            ]
        )

        all_values += [
            v
            for t in output.tables
            for r in t.rows
            for v in r.cells.values()
        ]

        all_values += [
            v
            for item in output.line_items
            for v in item.fields.values()
        ]

        if not any(
            v.value is not None
            for v in all_values
        ):
            raise AppError(
                'EXTRACTION_EMPTY',
                'No values could be grounded in the source text.',
                422,
            )

        return output