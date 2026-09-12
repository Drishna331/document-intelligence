import json
import unittest
import asyncio
from dataclasses import replace
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.services.model_client import GeminiClient
from .helpers import invoice_wire


class Response:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload or {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text':json.dumps(invoice_wire())}]}}]}
        self.content = self
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def iter_chunked(self, size): yield json.dumps(self.payload).encode()


class Transport:
    def __init__(self, response): self.response = response; self.body = None
    def post(self, url, **kwargs): self.body = kwargs; return self.response


class ModelClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = replace(Settings(), gemini_api_key='unit-test-key')

    async def test_structured_provider_request_contract(self):
        transport = Transport(Response())
        raw = await GeminiClient(self.settings, transport).generate('test prompt')
        self.assertIn('fields', json.loads(raw))
        config = transport.body['json']['generationConfig']
        self.assertEqual(config['responseMimeType'], 'application/json')
        self.assertIn('properties', config['responseJsonSchema'])
        self.assertNotIn('temperature', config)

    def test_default_model_is_gemini_3_8_flash(self):
        self.assertEqual(Settings().llm_model, 'gemini-3.8-flash')

    async def test_provider_error_statuses(self):
        for status in [401, 403, 429, 500, 503]:
            with self.subTest(status=status), self.assertRaises(AppError):
                await GeminiClient(self.settings, Transport(Response(status))).generate('test')

    async def test_truncated_response_is_not_accepted(self):
        payload = {'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]}
        with self.assertRaises(AppError) as ctx:
            await GeminiClient(self.settings, Transport(Response(payload=payload))).generate('test')
        self.assertEqual(ctx.exception.code, 'MODEL_INCOMPLETE_RESPONSE')

    async def test_timeout_is_controlled(self):
        class Timeout:
            def post(self, *args, **kwargs): raise asyncio.TimeoutError()
        with self.assertRaises(AppError) as ctx:
            await GeminiClient(self.settings, Timeout()).generate('test')
        self.assertEqual(ctx.exception.status, 504)

    async def test_response_size_limit(self):
        with self.assertRaises(AppError) as ctx:
            await GeminiClient(replace(self.settings, max_model_response_bytes=2), Transport(Response())).generate('test')
        self.assertEqual(ctx.exception.code, 'MODEL_RESPONSE_TOO_LARGE')
