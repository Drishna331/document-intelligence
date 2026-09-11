"""Regression tests for processing-status and numeric-value handoff."""
import unittest
from dataclasses import replace

from backend.app.core.config import Settings
from backend.app.schemas.extraction import SourcePage, WireDocument
from backend.app.services.document_service import DocumentService
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.financial_validation_service import FinancialValidationService
from .helpers import TEXT, invoice_wire, pdf_bytes


class LowConfidenceOCR:
    def extract(self, _data, _mime):
        return [SourcePage(page_number=1, text=TEXT, method='tesseract', ocr_mean_word_confidence=42)]


class StaticExtraction:
    async def extract(self, _document_type, pages):
        wire = WireDocument.model_validate(invoice_wire())
        return ExtractionService(None).ground('invoice', wire, pages)


class MemoryRepository:
    def __init__(self):
        self.results = []

    async def save(self, result):
        self.results.append(result)


class DocumentServiceRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_ocr_confidence_is_warning_not_processing_failure(self):
        repository = MemoryRepository()
        service = DocumentService(replace(Settings(), gemini_api_key='not-used'), LowConfidenceOCR(),
                                  StaticExtraction(), FinancialValidationService(), repository)
        result = await service.process(pdf_bytes(), 'invoice.pdf', 'application/pdf', 'invoice', 'test-request')
        self.assertEqual(result.processing_status, 'PASS')
        self.assertEqual(result.validation.overall_status, 'PASS')
        self.assertEqual(result.extracted_data.fields['total_amount'].numeric_value, '110.00')
        self.assertTrue(any('Low OCR confidence' in warning for warning in result.processing_metadata.warnings))
        self.assertEqual(repository.results, [result])

    async def test_numeric_value_is_available_to_financial_validation(self):
        pages = [SourcePage(page_number=1, text=TEXT, method='native')]
        extracted = await StaticExtraction().extract('invoice', pages)
        validation = FinancialValidationService().validate('invoice', extracted)
        self.assertEqual(extracted.fields['subtotal'].numeric_value, '100.00')
        self.assertEqual(next(c for c in validation.checks if c.name == 'invoice_tax_total').status, 'PASS')
