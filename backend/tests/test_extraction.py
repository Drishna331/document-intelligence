import json
import unittest
from backend.app.core.errors import AppError
from backend.app.schemas.extraction import SourcePage, WireDocument
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.financial_validation_service import FinancialValidationService
from .helpers import TEXT, invoice_wire, StubModel, wire_field


class ExtractionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pages = [SourcePage(page_number=1, text=TEXT, method='native')]
        self.service = ExtractionService(StubModel())

    async def test_schema_and_grounded_fields(self):
        result = await self.service.extract('invoice', self.pages)
        self.assertEqual(result.fields['total_amount'].numeric_value, '110.00')
        self.assertEqual(result.fields['total_amount'].evidence.page_number, 1)
        self.assertIsNone(result.fields['invoice_date'].value)

    def test_fake_evidence_is_rejected(self):
        wire = invoice_wire(); wire['fields'][-1]['content']['source_text'] = 'Invented total 110.00'
        result = self.service.ground('invoice', WireDocument(**wire), self.pages)
        self.assertIsNone(result.fields['total_amount'].value)
        self.assertTrue(result.warnings)

    def test_value_must_be_a_complete_source_token(self):
        wire = invoice_wire()
        wire['fields'][-1]['kind'] = 'text'
        wire['fields'][-1]['content']['raw_value'] = '11'
        result = self.service.ground('invoice', WireDocument(**wire), self.pages)
        self.assertIsNone(result.fields['total_amount'].value)

    def test_invoice_amounts_are_numeric_despite_incorrect_kind(self):
        wire = invoice_wire()
        wire['fields'][2]['kind'] = 'currency'
        wire['fields'][3]['kind'] = 'text'
        wire['fields'][4]['kind'] = 'text'
        wire['line_items'][0]['fields'][1]['kind'] = 'text'
        wire['line_items'][0]['fields'][2]['kind'] = 'currency'
        wire['line_items'][0]['fields'][3]['kind'] = 'text'

        result = self.service.ground('invoice', WireDocument(**wire), self.pages)

        self.assertEqual(result.fields['subtotal'].numeric_value, '100.00')
        self.assertEqual(result.fields['tax_amount'].numeric_value, '10.00')
        self.assertEqual(result.fields['total_amount'].numeric_value, '110.00')
        self.assertEqual(result.line_items[0].fields['quantity'].numeric_value, '2')
        self.assertEqual(result.line_items[0].fields['unit_price'].numeric_value, '50.00')
        self.assertEqual(result.line_items[0].fields['line_total'].numeric_value, '100.00')
        checks = FinancialValidationService().validate('invoice', result).checks
        self.assertEqual([check.status for check in checks[:3]], ['PASS'] * 3)

    def test_text_identifier_does_not_become_numeric(self):
        wire = invoice_wire()
        wire['fields'][0]['content']['raw_value'] = '12345'
        wire['fields'][0]['content']['source_text'] = 'Invoice number 12345'
        pages = [SourcePage(
            page_number=1,
            text=TEXT.replace('INV-TEST', '12345'),
            method='native',
        )]

        result = self.service.ground('invoice', WireDocument(**wire), pages)

        self.assertEqual(result.fields['invoice_number'].value, '12345')
        self.assertIsNone(result.fields['invoice_number'].numeric_value)

    def test_wrong_page_is_rejected(self):
        wire = invoice_wire(); wire['fields'][-1]['content']['page_number'] = 2
        result = self.service.ground('invoice', WireDocument(**wire), self.pages)
        self.assertIsNone(result.fields['total_amount'].value)

    def test_duplicate_fields_fail(self):
        wire = invoice_wire(); wire['fields'].append(wire['fields'][0])
        with self.assertRaises(AppError):
            self.service.ground('invoice', WireDocument(**wire), self.pages)

    def test_additional_meaningful_fields_preserved(self):
        wire = invoice_wire(); wire['fields'].append(wire_field('extra_vendor_label', 'Example Ltd', 'Vendor Example Ltd', 'text'))
        result = self.service.ground('invoice', WireDocument(**wire), self.pages)
        self.assertEqual(result.fields['extra_vendor_label'].value, 'Example Ltd')

    async def test_malformed_model_output(self):
        class Malformed:
            async def generate(self, _): return '{"fields":'
        with self.assertRaises(AppError) as ctx:
            await ExtractionService(Malformed()).extract('invoice', self.pages)
        self.assertEqual(ctx.exception.code, 'EXTRACTION_SCHEMA_ERROR')

    def test_periods_must_exist_in_source(self):
        wire = invoice_wire(); wire['periods'] = ['2099']
        with self.assertRaises(AppError):
            self.service.ground('balance_sheet', WireDocument(**wire), self.pages)
