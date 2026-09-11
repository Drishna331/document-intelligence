"""Deterministic Decimal arithmetic. Never adds missing operands as zero."""
from decimal import Decimal
from ..schemas.document import Check, Validation


def number(fields, key):
    field = fields.get(key)
    if field is None or field.numeric_value is None:
        return None
    value = Decimal(field.numeric_value)
    return value if value.is_finite() else None


def validation_check(name, fields, inputs, reported, tolerance, period=None,
                     operation='sum', reason=None):
    operands = {key: number(fields, key) for key, _ in inputs}
    actual = number(fields, reported)
    if operation == 'product':
        formula = ' × '.join(key for key, _ in inputs) + ' ≈ ' + reported
    else:
        formula = ' '.join(('' if i == 0 and sign == 1 else '+ ' if sign == 1 else '- ') + key
                           for i, (key, sign) in enumerate(inputs)) + ' ≈ ' + reported
    calculated = variance = None
    if len(operands) != len(inputs):
        reason = 'Duplicate component keys cannot be reconciled.'
    if not inputs:
        reason = reason or 'No complete source component group is available.'
    if any(x is None for x in operands.values()) or actual is None:
        reason = reason or 'A required source amount is missing, unreadable or ambiguous.'
    status = 'NOT_APPLICABLE'
    if reason is None:
        if operation == 'product':
            calculated = Decimal(1)
            for value in operands.values():
                calculated *= value
        else:
            calculated = sum((operands[key] * sign for key, sign in inputs), Decimal(0))
        variance = calculated - actual
        status = 'PASS' if abs(variance) <= tolerance else 'FAIL'
    return Check(name=name, period=period, formula=formula,
                 operands={k: str(v) if v is not None else None for k, v in operands.items()},
                 calculated_value=str(calculated) if calculated is not None else None,
                 reported_value=str(actual) if actual is not None else None,
                 variance=str(variance) if variance is not None else None,
                 tolerance=str(tolerance), status=status, reason=reason)


class FinancialValidationService:
    def __init__(self, tolerance='0.05'):
        self.tolerance = Decimal(tolerance)

    def validate(self, document_type, data):
        checks = []

        def add(name, fields, inputs, target, period=None, **kwargs):
            checks.append(validation_check(name, fields, inputs, target, self.tolerance, period, **kwargs))

        if document_type == 'invoice':
            fields = data.fields
            for index, item in enumerate(data.line_items, 1):
                target = 'net_amount' if number(item.fields, 'net_amount') is not None else 'line_total'
                reason = None
                if item.amount_basis != 'net':
                    reason = 'Quantity and unit price can only be compared to an explicitly net amount.'
                if number(item.fields, 'discount') is not None:
                    reason = 'A line discount is present; the simple quantity × unit price check does not apply.'
                add(f'line_{index}_quantity_price', item.fields,
                    [('quantity', 1), ('unit_price', 1)], target, operation='product', reason=reason)
            sum_fields = dict(fields)
            inputs = []
            valid_basis = data.line_items_complete and bool(data.line_items)
            for index, item in enumerate(data.line_items):
                key = f'line_{index + 1}'
                value = item.fields.get('net_amount') or item.fields.get('line_total')
                if value:
                    sum_fields[key] = value
                inputs.append((key, 1))
                valid_basis = valid_basis and item.amount_basis == 'net'
            add('invoice_line_sum', sum_fields, inputs, 'subtotal',
                reason=None if valid_basis else 'A complete set of comparable net line amounts is required.')
            target = 'taxable_amount' if number(fields, 'taxable_amount') is not None else 'subtotal'
            components = [(target, 1), ('tax_amount', 1)]
            # Taxable amount is already after discounts. Only subtract a reported
            # discount when using a pre-discount subtotal and its basis is explicit.
            discount = fields.get('discount')
            if target == 'subtotal' and discount and (discount.value is not None or discount.evidence is not None):
                components.append(('discount', -1))
            for key in ['shipping_amount', 'other_charges', 'rounding_adjustment']:
                if key in fields:
                    components.append((key, 1))
            add('invoice_tax_total', fields, components, 'total_amount',
                reason=None if data.tax_basis == 'exclusive' else
                'Tax is included in the displayed total or its basis is unknown; do not add tax again.')
            add('invoice_cash_change', fields, [('cash_paid', 1), ('total_amount', -1)], 'change')
        else:
            for period in data.periods:
                f, p = period.fields, period.period
                if document_type == 'balance_sheet':
                    if number(f, 'total_capital_and_liabilities') is not None:
                        add('balance_sheet_equation', f, [('total_capital_and_liabilities', 1)], 'total_assets', p)
                    else:
                        add('balance_sheet_equation', f, [('total_liabilities', 1), ('total_equity', 1)], 'total_assets', p)
                    for target in ['total_assets', 'total_capital_and_liabilities']:
                        group = next((g for g in data.reconciliations if g.period == p and g.total_key == target), None)
                        keys = [(k, 1) for k in group.component_keys] if group else []
                        reason = None if group and group.complete and target not in group.component_keys else 'A complete, non-overlapping component group is required.'
                        add(target + '_components', f, keys, target, p, reason=reason)
                elif document_type == 'profit_and_loss':
                    rules = [
                        ('income', [('interest_earned', 1), ('other_income', 1)], 'total_income'),
                        ('expenditure', [('interest_expended', 1), ('operating_expenses', 1), ('provisions_and_contingencies', 1)], 'total_expenditure'),
                        ('profit_before_minority', [('total_income', 1), ('total_expenditure', -1)], 'profit_before_minority_interest'),
                        ('group_profit', [('profit_before_minority_interest', 1), ('minority_interest', -1)], 'net_profit'),
                    ]
                    for name, terms, target in rules:
                        add(name, f, terms, target, p)
                    terms = [('net_profit', 1), ('brought_forward_profit', 1)]
                    if 'appropriation_adjustment' in f:
                        terms.append(('appropriation_adjustment', 1))
                    add('available_for_appropriation', f, terms, 'total_available_for_appropriation', p)
                    for name, terms, target in [
                        ('gross_profit', [('revenue', 1), ('cost_of_sales', -1)], 'gross_profit'),
                        ('operating_profit', [('gross_profit', 1), ('operating_expenses', -1)], 'operating_profit'),
                    ]:
                        add(name, f, terms, target, p)
                else:
                    add('cash_flow_net_change', f, [('operating_cash_flow', 1), ('investing_cash_flow', 1),
                        ('financing_cash_flow', 1), ('fx_adjustment', 1)], 'net_change_in_cash', p)
                    terms = [('opening_cash', 1), ('net_change_in_cash', 1)]
                    # When an adjustment row exists it is an operand even when
                    # unreadable. If no such row exists the two-term formula applies.
                    for key in ['cash_acquired', 'other_cash_adjustments']:
                        if key in f:
                            terms.append((key, 1))
                    add('cash_flow_closing_cash', f, terms, 'closing_cash', p)
        statuses = [c.status for c in checks]
        overall = 'FAIL' if 'FAIL' in statuses else 'PASS' if 'PASS' in statuses else 'NOT_APPLICABLE'
        issues = [f'{c.period + ": " if c.period else ""}{c.name}: variance {c.variance}' for c in checks if c.status == 'FAIL']
        return Validation(checks=checks, overall_status=overall, issues=issues)
