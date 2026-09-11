import json
import unittest
from backend.app.core.errors import AppError
from backend.app.schemas.extraction import SourcePage, WireDocument
from backend.app.services.extraction_service import ExtractionService
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
        wire = invoice_wire(); wire['fields'][-1]['content']['raw_value'] = '11'
        result = self.service.ground('invoice', WireDocument(**wire), self.pages)
        self.assertIsNone(result.fields['total_amount'].value)

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
