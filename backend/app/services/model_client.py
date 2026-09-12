import asyncio
import json
import re
import aiohttp
from ..core.errors import AppError
from ..schemas.extraction import WireDocument
from .prompts import SYSTEM_PROMPT


class GeminiClient:
    """REST client kept small so request/response/error contracts can be tested."""
    def __init__(self, settings, session):
        self.settings, self.session = settings, session

    async def generate(self, prompt):
        if not self.settings.gemini_api_key:
            raise AppError('MODEL_NOT_CONFIGURED', 'Structured extraction is unavailable: configure GEMINI_API_KEY on the server.', 503)
        if not re.fullmatch(r'[A-Za-z0-9._-]+', self.settings.llm_model):
            raise AppError('MODEL_CONFIGURATION_ERROR', 'The model configuration is invalid.', 503)
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.settings.llm_model}:generateContent'
        body = {
            'systemInstruction': {'parts': [{'text': SYSTEM_PROMPT}]},
            'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'maxOutputTokens': 32768,
                                 'responseMimeType': 'application/json',
                                 'responseJsonSchema': WireDocument.model_json_schema()},
        }
        try:
            # Gemini explicitly labels 429/5xx as transient.  Retry a small,
            # bounded number of times so a single capacity spike does not become
            # an application failure, while preserving a controlled failure when
            # the provider remains unavailable.
            for attempt in range(3):
                async with self.session.post(url, json=body,
                        headers={'x-goog-api-key': self.settings.gemini_api_key},
                        timeout=aiohttp.ClientTimeout(total=self.settings.llm_timeout_seconds)) as response:
                    # Provider error bodies can include request diagnostics or source
                    # fragments.  Do not log or expose them; status is sufficient.
                    if response.status in (429, 500, 502, 503, 504):
                        if attempt < 2:
                            await asyncio.sleep(1 + attempt)
                            continue
                        raise AppError('MODEL_UNAVAILABLE', 'The extraction provider is busy or unavailable. Try again later.', 503)
                    if response.status != 200:
                        raise AppError('MODEL_REQUEST_FAILED', 'The model rejected the request. Check server credentials and model configuration.', 503)
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > self.settings.max_model_response_bytes:
                            raise AppError('MODEL_RESPONSE_TOO_LARGE', 'The extraction response exceeded its safety limit.', 502)
                        chunks.append(chunk)
                    payload = json.loads(b''.join(chunks))
                    break
            candidate = payload['candidates'][0]
            if candidate.get('finishReason') != 'STOP':
                raise AppError('MODEL_INCOMPLETE_RESPONSE', 'The extraction response was incomplete or blocked.', 502)
            text = ''.join(part.get('text', '') for part in candidate['content']['parts'] if not part.get('thought'))
            return text
        except AppError:
            raise
        except asyncio.TimeoutError:
            raise AppError('MODEL_TIMEOUT', 'Structured extraction timed out. Please retry.', 504) from None
        except aiohttp.ClientError:
            raise AppError('MODEL_UNAVAILABLE', 'The extraction provider could not be reached.', 503) from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise AppError('MODEL_INVALID_RESPONSE', 'The extraction provider returned an invalid response.', 502) from None


class OpenAIClient:
    """OpenAI Structured Outputs adapter returning the same WireDocument JSON."""
    def __init__(self, settings, session):
        self.settings, self.session = settings, session

    async def generate(self, prompt):
        if not self.settings.openai_api_key:
            raise AppError('MODEL_NOT_CONFIGURED', 'Structured extraction is unavailable: configure OPENAI_API_KEY on the server.', 503)
        body = {'model': self.settings.llm_model, 'temperature': 0,
                'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_schema', 'json_schema': {'name': 'wire_document', 'strict': True,
                    'schema': WireDocument.model_json_schema()}}}
        try:
            async with self.session.post('https://api.openai.com/v1/chat/completions', json=body,
                headers={'Authorization': 'Bearer ' + self.settings.openai_api_key},
                timeout=aiohttp.ClientTimeout(total=self.settings.llm_timeout_seconds)) as response:
                if response.status in (429, 500, 502, 503, 504):
                    raise AppError('MODEL_UNAVAILABLE', 'The extraction provider is busy or unavailable. Try again later.', 503)
                if response.status != 200:
                    raise AppError('MODEL_REQUEST_FAILED', 'The model rejected the request. Check server credentials and model configuration.', 503)
                payload = await response.json()
            content = payload['choices'][0]['message']['content']
            if not content:
                raise AppError('MODEL_INCOMPLETE_RESPONSE', 'The extraction provider returned no structured output.', 502)
            return content
        except AppError:
            raise
        except asyncio.TimeoutError:
            raise AppError('MODEL_TIMEOUT', 'Structured extraction timed out. Please retry.', 504) from None
        except aiohttp.ClientError:
            raise AppError('MODEL_UNAVAILABLE', 'The extraction provider could not be reached.', 503) from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise AppError('MODEL_INVALID_RESPONSE', 'The extraction provider returned an invalid response.', 502) from None


def create_model_client(settings, session):
    if settings.llm_provider == 'openai':
        return OpenAIClient(settings, session)
    if settings.llm_provider == 'gemini':
        return GeminiClient(settings, session)
    raise ValueError('LLM_PROVIDER must be gemini or openai')
