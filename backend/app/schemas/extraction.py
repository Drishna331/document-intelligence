from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal['invoice', 'balance_sheet', 'profit_and_loss', 'cash_flow_statement']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SourcePage(StrictModel):
    page_number: int
    text: str
    method: Literal['native', 'tesseract']
    rotation_applied: int = 0
    ocr_mean_word_confidence: float | None = None


class Evidence(StrictModel):
    source_text: str
    page_number: int


class Value(StrictModel):
    value: str | None = None
    numeric_value: str | None = None
    evidence: Evidence | None = None
    reason: str | None = None


class WireValue(StrictModel):
    raw_value: str | None
    page_number: int | None
    source_text: str | None


class WireField(StrictModel):
    key: str = Field(description='Stable snake_case semantic name; add keys for all other visible information')
    label: str = Field(description='Original source label')
    period: str | None = Field(description='Exact printed year/period; null for document metadata')
    kind: Literal['text', 'number', 'date', 'currency', 'percentage']
    content: WireValue


class WireCell(StrictModel):
    column: str = Field(description='Exact printed column header or reporting year')
    kind: Literal['text', 'number', 'percentage']
    content: WireValue


class WireRow(StrictModel):
    label: str
    key: str | None = Field(description='Canonical financial key when semantically clear; otherwise null')
    section: str | None
    role: Literal['detail', 'subtotal', 'total', 'note', 'header']
    cells: list[WireCell]


class WireTable(StrictModel):
    title: str
    columns: list[str]
    rows: list[WireRow]


class WireLineItem(StrictModel):
    fields: list[WireField] = Field(description='Description, quantity, unit_price, line_total, net_amount, tax, discount and all other visible columns')
    amount_basis: Literal['net', 'gross', 'unknown']


class WireReconciliation(StrictModel):
    period: str | None
    total_key: str
    component_keys: list[str]
    complete: bool = Field(description='True ONLY for a complete, explicitly grouped, non-overlapping set of source components; never infer missing items')


class WireDocument(StrictModel):
    fields: list[WireField]
    periods: list[str]
    tables: list[WireTable]
    line_items: list[WireLineItem]
    reconciliations: list[WireReconciliation]
    tax_basis: Literal['exclusive', 'inclusive', 'unknown']
    line_items_complete: bool
    warnings: list[str]


class TableRow(StrictModel):
    label: str
    key: str | None
    section: str | None
    role: str
    cells: dict[str, Value]


class Table(StrictModel):
    title: str
    columns: list[str]
    rows: list[TableRow]


class LineItem(StrictModel):
    fields: dict[str, Value]
    amount_basis: str


class Period(StrictModel):
    period: str
    fields: dict[str, Value]


class ExtractedData(StrictModel):
    fields: dict[str, Value] = Field(default_factory=dict)
    periods: list[Period] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    line_items: list[LineItem] = Field(default_factory=list)
    reconciliations: list[WireReconciliation] = Field(default_factory=list)
    tax_basis: str = 'unknown'
    line_items_complete: bool = False
    warnings: list[str] = Field(default_factory=list)


MINIMUM_FIELDS = {
    'invoice': ['invoice_number', 'invoice_date', 'vendor_name', 'customer_name', 'currency',
                'subtotal', 'tax_amount', 'discount', 'total_amount'],
    'balance_sheet': ['total_assets', 'total_liabilities', 'total_equity', 'total_capital_and_liabilities'],
    'profit_and_loss': ['revenue', 'cost_of_sales', 'gross_profit', 'operating_expenses',
                        'operating_profit', 'tax', 'net_profit'],
    'cash_flow_statement': ['operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow',
                           'opening_cash', 'net_change_in_cash', 'closing_cash'],
}
