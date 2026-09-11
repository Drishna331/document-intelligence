import io
import json
import fitz
from PIL import Image
from backend.app.schemas.extraction import Value, WireDocument

TEXT = 'Invoice number INV-TEST\nVendor Example Ltd\nSubtotal 100.00\nTax 10.00\nTotal 110.00\nService A quantity 2 unit price 50.00 net amount 100.00'


def pdf_bytes(text=TEXT, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((40, 40), text)
    result = doc.tobytes()
    doc.close()
    return result


def image_bytes(format='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(output, format=format)
    return output.getvalue()


def v(amount):
    return Value(value=str(amount) if amount is not None else None,
                 numeric_value=str(amount) if amount is not None else None)


def wire_field(key, raw, quote, kind='number', period=None, page=1):
    return {'key': key, 'label': key, 'kind': kind, 'period': period,
            'content': {'raw_value': raw, 'source_text': quote, 'page_number': page}}


def invoice_wire():
    return {'fields': [
        wire_field('invoice_number', 'INV-TEST', 'Invoice number INV-TEST', 'text'),
        wire_field('vendor_name', 'Example Ltd', 'Vendor Example Ltd', 'text'),
        wire_field('subtotal', '100.00', 'Subtotal 100.00'),
        wire_field('tax_amount', '10.00', 'Tax 10.00'),
        wire_field('total_amount', '110.00', 'Total 110.00')],
        'periods': [], 'tables': [], 'line_items': [{'amount_basis': 'net', 'fields': [
            wire_field('description', 'Service A', 'Service A quantity 2 unit price 50.00 net amount 100.00', 'text'),
            wire_field('quantity', '2', 'Service A quantity 2 unit price 50.00 net amount 100.00'),
            wire_field('unit_price', '50.00', 'Service A quantity 2 unit price 50.00 net amount 100.00'),
            wire_field('line_total', '100.00', 'Service A quantity 2 unit price 50.00 net amount 100.00')]}],
        'reconciliations': [], 'tax_basis': 'exclusive', 'line_items_complete': True, 'warnings': []}


class StubModel:
    """Synthetic test double only. Never selected from production configuration."""
    async def generate(self, prompt):
        return json.dumps(invoice_wire())
