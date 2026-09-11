import shutil
from urllib.parse import unquote
from aiohttp import web
from ...core.errors import AppError
from ...schemas.extraction import DocumentType

STATE = web.AppKey('document_intelligence_state', object)


def response(model, status=200):
    return web.json_response(model.model_dump(mode='json'), status=status)


async def health(request):
    state = request.app[STATE]
    await state['database'].execute('SELECT 1')
    settings = state['settings']
    model = bool(settings.openai_api_key if settings.llm_provider == 'openai' else settings.gemini_api_key)
    ocr = bool(shutil.which('tesseract'))
    ready = model and ocr
    return web.json_response({'status': 'ok', 'database': 'ok', 'ocr_available': ocr,
        'model_configured': model, 'ready_for_processing': ready,
        'max_upload_bytes': state['settings'].max_upload_bytes, 'max_pages': 3},
        status=503 if request.query.get('ready') == 'true' and not ready else 200)


async def process(request):
    state = request.app[STATE]
    settings = state['settings']
    if request.content_type != 'multipart/form-data':
        raise AppError('INVALID_MULTIPART', 'Send multipart/form-data with file and document_type.', 415)
    data = None
    filename = mime = document_type = None
    try:
        reader = await request.multipart()
        count = 0
        async for part in reader:
            count += 1
            if count > 2 or part.name not in ('file', 'document_type'):
                raise AppError('INVALID_FORM', 'Exactly file and document_type are accepted.', 422)
            if part.name == 'file':
                if data is not None or not part.filename:
                    raise AppError('INVALID_FORM', 'Provide exactly one named file.', 422)
                filename, mime = unquote(part.filename), part.headers.get('Content-Type', '')
                chunks = bytearray()
                while True:
                    chunk = await part.read_chunk(65536)
                    if not chunk:
                        break
                    if len(chunks) + len(chunk) > settings.max_upload_bytes:
                        raise AppError('FILE_TOO_LARGE', 'The upload exceeds the configured file size limit.', 413)
                    chunks.extend(chunk)
                data = bytes(chunks)
            else:
                if document_type is not None or part.filename:
                    raise AppError('INVALID_FORM', 'Provide one document_type text field.', 422)
                value = bytearray()
                while True:
                    chunk = await part.read_chunk(8192)
                    if not chunk:
                        break
                    value.extend(chunk)
                    if len(value) > 64:
                        raise AppError('INVALID_DOCUMENT_TYPE', 'The selected document type is invalid.', 422)
                document_type = bytes(value).decode('utf-8').strip()
    except AppError:
        raise
    except (ValueError, AssertionError, UnicodeError):
        raise AppError('INVALID_MULTIPART', 'The multipart upload could not be read.', 400) from None
    if data is None or document_type not in DocumentType.__args__:
        raise AppError('INVALID_FORM', 'Provide file and a supported document_type.', 422)
    if state['slots'].locked():
        raise AppError('PROCESSOR_BUSY', 'Another document is processing. Try again shortly.', 429)
    async with state['slots']:
        result = await state['service'].process(data, filename, mime, document_type, request['request_id'])
    return response(result, 201)


async def get_document(request):
    return response(await request.app[STATE]['repository'].get(request.match_info['document_name']))


async def list_documents(request):
    try:
        limit, offset = int(request.query.get('limit', '20')), int(request.query.get('offset', '0'))
    except ValueError:
        raise AppError('INVALID_PAGINATION', 'limit and offset must be integers.', 422) from None
    search = request.query.get('q', '')
    if not 1 <= limit <= 100 or offset < 0 or len(search) > 180:
        raise AppError('INVALID_PAGINATION', 'Use limit 1–100, offset >= 0 and a short filename search.', 422)
    return response(await request.app[STATE]['repository'].list(limit, offset, search))


def add_routes(app):
    app.router.add_get('/api/v1/health', health)
    app.router.add_post('/api/v1/documents/process', process)
    app.router.add_get('/api/v1/documents', list_documents)
    app.router.add_get('/api/v1/documents/{document_name}', get_document)
