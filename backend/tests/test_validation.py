import unittest
from dataclasses import replace
from decimal import Decimal
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.services.document_validation_service import validate_file, sanitize_filename
from backend.app.services.ocr_service import OCRService
from backend.app.utils.numbers import parse_number
from .helpers import pdf_bytes, image_bytes


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()

    def test_valid_native_pdf(self):
        result = validate_file(pdf_bytes(), 'invoice.pdf', 'application/pdf', self.settings)
        self.assertEqual((result.status, result.page_count), ('PASS', 1))

    def test_three_pages_accepted(self):
        self.assertEqual(validate_file(pdf_bytes(pages=3), 'a.pdf', '', self.settings).page_count, 3)

    def test_four_pages_rejected(self):
        with self.assertRaises(AppError) as ctx:
            validate_file(pdf_bytes(pages=4), 'a.pdf', '', self.settings)
        self.assertEqual(ctx.exception.code, 'PAGE_LIMIT_EXCEEDED')

    def test_png_and_jpeg(self):
        for ext, mime, format in [('png', 'image/png', 'PNG'), ('jpg', 'image/jpeg', 'JPEG'), ('jpeg', 'image/jpeg', 'JPEG')]:
            with self.subTest(ext=ext):
                self.assertEqual(validate_file(image_bytes(format), 'a.' + ext, mime, self.settings).status, 'PASS')

    def test_empty_corrupt_and_unsupported(self):
        for data, name, code in [(b'', 'a.pdf', 'EMPTY_FILE'), (b'not pdf', 'a.pdf', 'INVALID_FILE_SIGNATURE'),
                                 (b'%PDF-1.4\ncorrupt\n%%EOF', 'a.pdf', 'CORRUPTED_FILE'),
                                 (b'abc', 'file.txt', 'UNSUPPORTED_FILE_TYPE'),
                                 (b'\x89PNG\r\n\x1a\nbroken', 'a.png', 'CORRUPTED_FILE')]:
            with self.subTest(code=code), self.assertRaises(AppError) as ctx:
                validate_file(data, name, '', self.settings)
            self.assertEqual(ctx.exception.code, code)

    def test_spoofed_mime_and_signature(self):
        for data, mime in [(pdf_bytes(), 'image/png'), (image_bytes(), 'application/pdf')]:
            with self.assertRaises(AppError):
                validate_file(data, 'a.pdf', mime, self.settings)

    def test_file_size_limit(self):
        with self.assertRaises(AppError) as ctx:
            validate_file(pdf_bytes(), 'a.pdf', '', replace(self.settings, max_upload_bytes=10))
        self.assertEqual(ctx.exception.status, 413)

    def test_image_pixel_limit(self):
        with self.assertRaises(AppError) as ctx:
            validate_file(image_bytes(), 'a.png', '', replace(self.settings, max_image_pixels=10))
        self.assertEqual(ctx.exception.code, 'IMAGE_TOO_LARGE')

    def test_path_sanitization(self):
        self.assertEqual(sanitize_filename('../../folder/Invoice.pdf'), 'Invoice.pdf')
        self.assertEqual(sanitize_filename('C:\\secret\\test.jpg'), 'test.jpg')
        self.assertNotIn('<', sanitize_filename('<script>.png'))

    def test_native_pdf_skips_ocr(self):
        ocr = OCRService(self.settings)
        ocr._image = lambda *_: self.fail('Native PDF incorrectly sent to OCR')
        pages = ocr.extract(pdf_bytes(), 'application/pdf')
        self.assertEqual(pages[0].method, 'native')
        self.assertIn('110.00', pages[0].text)

    def test_numbers(self):
        cases = [('1,250.00', None, '1250.00'), ('(1,250)', '.', '-1250'),
                 ('[1.250,20]', ',', '-1250.20'), ('₹ 12,345.50', None, '12345.50'),
                 ('126,27', None, '126.27'), ('-12.30', None, '-12.30'),
                 ('1,23,456.78', '.', '123456.78'), ('1 250,00', ',', '1250.00')]
        for raw, separator, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_number(raw, separator), Decimal(expected))

    def test_ambiguous_missing_and_nonfinite_numbers(self):
        for value in [None, True, 'NaN', 'Infinity', '-', '1,250', '1.234', '12.3.4', '1 2', '10%']:
            with self.subTest(value=value):
                self.assertIsNone(parse_number(value))
        self.assertEqual(parse_number('10%', percentage=True), Decimal('10'))
