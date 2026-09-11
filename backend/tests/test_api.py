import json
import tempfile
from pathlib import Path
from dataclasses import replace
import aiohttp
from aiohttp.test_utils import AioHTTPTestCase
from backend.app.main import create_app
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.api.routes.documents import STATE
from backend.app.core.database import Database
from backend.app.repositories.document_repository import DocumentRepository
from backend.app.services.extraction_service import ExtractionService
from .helpers import pdf_bytes, StubModel, invoice_wire


class APITests(AioHTTPTestCase):
    async def get_application(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = replace(Settings(), database_path=str(Path(self.directory.name) / 'test.sqlite3'))
        return create_app(self.settings, model_client=StubModel())

    def form(self, data=None, name='invoice.pdf', mime='application/pdf', document_type='invoice'):
        form = aiohttp.FormData()
        form.add_field('document_type', document_type)
        form.add_field('file', pdf_bytes() if data is None else data, filename=name, content_type=mime)
        return form

    async def test_processing_get_list_health_and_latest_result(self):
        result = await self.client.post('/api/v1/documents/process', data=self.form())
        self.assertEqual(result.status, 201, await result.text())
        body = await result.json()
        self.assertEqual(body['processing_status'], 'PASS')
        self.assertEqual(body['extracted_data']['fields']['total_amount']['numeric_value'], '110.00')
        self.assertFalse(body['processing_metadata']['ocr_used'])
        self.assertIn('X-Request-ID', result.headers)
        get = await self.client.get('/api/v1/documents/invoice.pdf')
        self.assertEqual(await get.json(), body)
        listing = await (await self.client.get('/api/v1/documents')).json()
        self.assertEqual(listing['total'], 1)
        second = await self.client.post('/api/v1/documents/process', data=self.form())
        second_body = await second.json()
        self.assertNotEqual(body['processing_metadata']['request_id'], second_body['processing_metadata']['request_id'])
        latest = await (await self.client.get('/api/v1/documents/invoice.pdf')).json()
        self.assertEqual(latest, second_body)
        self.assertEqual((await (await self.client.get('/api/v1/documents')).json())['total'], 1)
        self.assertEqual((await self.client.get('/api/v1/health')).status, 200)

    async def test_persistence_new_database_instance(self):
        await self.client.post('/api/v1/documents/process', data=self.form())
        database = Database(self.settings, None)
        await database.initialize()
        result = await DocumentRepository(database).get('invoice.pdf')
        self.assertEqual(result.processing_status, 'PASS')

    async def test_filename_spaces_are_retrievable(self):
        result = await self.client.post('/api/v1/documents/process', data=self.form(name='Balance Sheet 2025.pdf'))
        body = await result.json()
        self.assertEqual(body['document_name'], 'Balance Sheet 2025.pdf')
        response = await self.client.get('/api/v1/documents/Balance%20Sheet%202025.pdf')
        self.assertEqual(response.status, 200)

    async def test_missing_filename_returns_404(self):
        result = await self.client.get('/api/v1/documents/missing.pdf')
        self.assertEqual(result.status, 404)
        self.assertEqual((await result.json())['error']['code'], 'DOCUMENT_NOT_FOUND')

    async def test_unsupported_file_has_controlled_error_and_saved_failure(self):
        result = await self.client.post('/api/v1/documents/process', data=self.form(b'hello', 'bad.txt', 'text/plain'))
        body = await result.json()
        self.assertEqual(result.status, 415)
        self.assertEqual(body['processing_status'], 'FAILED')
        self.assertIsNone(body['result']['extracted_data'])
        self.assertEqual((await self.client.get('/api/v1/documents/bad.txt')).status, 200)

    async def test_invalid_form_and_document_type(self):
        result = await self.client.post('/api/v1/documents/process', data=self.form(document_type='unknown'))
        self.assertEqual(result.status, 422)
        result = await self.client.post('/api/v1/documents/process', json={'file': 'bad'})
        self.assertEqual(result.status, 415)

    async def test_malformed_multipart(self):
        result = await self.client.post('/api/v1/documents/process', data=b'broken', headers={'Content-Type':'multipart/form-data; boundary=bad'})
        self.assertEqual(result.status, 400)

    async def test_missing_model_key_controlled_failure(self):
        from backend.app.services.model_client import GeminiClient
        self.app[STATE]['service'].extraction = ExtractionService(GeminiClient(self.settings, None))
        result = await self.client.post('/api/v1/documents/process', data=self.form())
        body = await result.json()
        self.assertEqual(result.status, 503)
        self.assertEqual(body['error']['code'], 'MODEL_NOT_CONFIGURED')
        self.assertTrue(body['result']['processing_metadata']['pages'])
        self.assertEqual(body['result']['processing_status'], 'FAILED')

    async def test_model_timeout(self):
        class Timeout:
            async def generate(self, _): raise AppError('MODEL_TIMEOUT', 'Extraction timed out.', 504)
        self.app[STATE]['service'].extraction = ExtractionService(Timeout())
        result = await self.client.post('/api/v1/documents/process', data=self.form())
        self.assertEqual(result.status, 504)
        self.assertEqual((await result.json())['processing_status'], 'FAILED')

    async def test_database_error_redacted(self):
        async def fail(_): raise AppError('DATABASE_ERROR', 'Database unavailable.', 503)
        self.app[STATE]['repository'].save = fail
        result = await self.client.post('/api/v1/documents/process', data=self.form())
        self.assertEqual(result.status, 503)
        self.assertNotIn('Traceback', await result.text())

    async def test_unexpected_failure_redacted(self):
        class BadOCR:
            def extract(self, *_): raise RuntimeError('secret-in-exception')
        self.app[STATE]['service'].ocr = BadOCR()
        result = await self.client.post('/api/v1/documents/process', data=self.form())
        self.assertEqual(result.status, 500)
        self.assertNotIn('secret-in-exception', await result.text())

    async def test_pagination_and_search(self):
        await self.client.post('/api/v1/documents/process', data=self.form())
        self.assertEqual((await self.client.get('/api/v1/documents?limit=101')).status, 422)
        self.assertEqual((await self.client.get('/api/v1/documents?offset=x')).status, 422)
        result = await (await self.client.get('/api/v1/documents?q=NO_MATCH')).json()
        self.assertEqual(result['total'], 0)

    async def test_openapi_and_frontend_assets(self):
        for path in ['/', '/results', '/docs', '/static/js/app.js', '/static/css/app.css', '/openapi.json']:
            self.assertEqual((await self.client.get(path)).status, 200, path)
        schema = await (await self.client.get('/openapi.json')).json()
        self.assertEqual(schema['openapi'], '3.1.0')
        self.assertEqual(len(schema['paths']), 4)
        self.assertIn('DocumentResult', schema['components']['schemas'])

    async def test_financial_failure_is_not_processing_pass(self):
        class WrongTotal:
            async def generate(self, _):
                wire = invoice_wire(); wire['fields'][-1]['content'] = {'raw_value':'111.00', 'source_text':'Total 111.00', 'page_number':1}
                return json.dumps(wire)
        self.app[STATE]['service'].extraction = ExtractionService(WrongTotal())
        data = pdf_bytes('Invoice number INV-TEST\nVendor Example Ltd\nSubtotal 100.00\nTax 10.00\nTotal 111.00\nService A quantity 2 unit price 50.00 net amount 100.00')
        result = await self.client.post('/api/v1/documents/process', data=self.form(data))
        self.assertEqual(result.status, 201)
        body = await result.json()
        self.assertEqual(body['processing_status'], 'FAILED')
        self.assertEqual(body['validation']['overall_status'], 'FAIL')
