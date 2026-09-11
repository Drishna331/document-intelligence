import io
import shutil
import unittest
import fitz
from PIL import Image
from backend.app.core.config import Settings
from backend.app.services.ocr_service import OCRService
from .helpers import pdf_bytes


@unittest.skipUnless(shutil.which('tesseract'), 'Tesseract is not installed')
class OCRIntegrationTests(unittest.TestCase):
    def image(self):
        document = fitz.open(stream=pdf_bytes(), filetype='pdf')
        pix = document[0].get_pixmap(dpi=200)
        im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        document.close()
        return im

    def test_real_png_ocr(self):
        stream = io.BytesIO(); self.image().save(stream, 'PNG')
        pages = OCRService(Settings()).extract(stream.getvalue(), 'image/png')
        self.assertIn('110.00', pages[0].text)
        self.assertEqual(pages[0].method, 'tesseract')

    def test_scanned_pdf_uses_ocr(self):
        im = self.image(); stream = io.BytesIO(); im.save(stream, 'PNG')
        pdf = fitz.open(); page = pdf.new_page(); page.insert_image(page.rect, stream=stream.getvalue())
        data = pdf.tobytes(); pdf.close()
        pages = OCRService(Settings()).extract(data, 'application/pdf')
        self.assertEqual(pages[0].method, 'tesseract')
        self.assertIn('110.00', pages[0].text)
