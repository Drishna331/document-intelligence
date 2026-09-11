"""One Python process serves the API, dashboard and OpenAPI documentation."""
import asyncio
import uuid
import aiohttp
from aiohttp import web
from .core.config import Settings, ROOT
from .core.errors import AppError
from .core.logging import configure_logging, event
from .core.database import Database
from .repositories.document_repository import DocumentRepository
from .services.ocr_service import OCRService
from .services.model_client import create_model_client
from .services.extraction_service import ExtractionService
from .services.financial_validation_service import FinancialValidationService
from .services.document_service import DocumentService
from .api.routes.documents import STATE, add_routes
from .api.openapi import specification


@web.middleware
async def boundary(request, handler):
    request['request_id'] = uuid.uuid4().hex
    settings = request.app[STATE]['settings']
    event('request_received', request['request_id'], method=request.method,
          route=request.path if not request.path.startswith('/api/v1/documents/') else '/api/v1/documents/{name_or_action}')
    origin = request.headers.get('Origin')
    allowed_origin = origin if origin in settings.allowed_origins else None
    try:
        if request.content_length and request.content_length > settings.max_upload_bytes + 1024 * 1024:
            raise AppError('FILE_TOO_LARGE', 'The upload exceeds the configured file size limit.', 413)
        if request.method == 'OPTIONS' and allowed_origin:
            result = web.Response(status=204)
        else:
            result = await handler(request)
    except AppError as exc:
        event('request_failure', request['request_id'], error_code=exc.code)
        result = web.json_response(exc.payload(request['request_id']), status=exc.status)
    except web.HTTPException as exc:
        result = web.json_response(AppError('HTTP_ERROR', exc.reason, exc.status).payload(request['request_id']), status=exc.status)
    except Exception as exc:
        event('request_failure', request['request_id'], error_code='INTERNAL_ERROR', exception_type=type(exc).__name__)
        result = web.json_response(AppError('INTERNAL_ERROR', 'The request could not be completed.', 500).payload(request['request_id']), status=500)
    result.headers['X-Request-ID'] = request['request_id']
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'no-referrer'
    result.headers['Cache-Control'] = 'no-store'
    result.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    if allowed_origin:
        result.headers['Access-Control-Allow-Origin'] = allowed_origin
        result.headers['Vary'] = 'Origin'
        result.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
        result.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return result


def create_app(settings=None, model_client=None, ocr_service=None):
    settings = settings or Settings.from_env()
    configure_logging()
    app = web.Application(client_max_size=settings.max_upload_bytes + 1024 * 1024, middlewares=[boundary])
    state = {'settings': settings, 'slots': asyncio.Semaphore(settings.max_concurrent_documents)}
    app[STATE] = state

    async def lifecycle(app):
        async with aiohttp.ClientSession() as session:
            database = Database(settings, session)
            await database.initialize()
            repository = DocumentRepository(database)
            extraction = ExtractionService(model_client or create_model_client(settings, session))
            service = DocumentService(settings, ocr_service or OCRService(settings), extraction,
                                       FinancialValidationService(settings.financial_tolerance), repository)
            state.update(database=database, repository=repository, service=service)
            yield

    app.cleanup_ctx.append(lifecycle)
    add_routes(app)

    async def dashboard(request):
        return web.FileResponse(ROOT / 'frontend/templates/dashboard.html')

    async def docs(request):
        return web.FileResponse(ROOT / 'frontend/templates/api_docs.html')

    async def openapi(request):
        return web.json_response(specification())

    app.router.add_get('/', dashboard)
    app.router.add_get('/results', dashboard)
    app.router.add_get('/docs', docs)
    app.router.add_get('/openapi.json', openapi)
    app.router.add_static('/static/', ROOT / 'frontend/static', show_index=False, follow_symlinks=False)
    return app


def main():
    try:
        settings = Settings.from_env()
    except (ValueError, TypeError):
        raise SystemExit('Invalid environment configuration. Check .env.example; no secret values have been logged.') from None
    web.run_app(create_app(settings), host=settings.host, port=settings.port, access_log=None,
                handler_cancellation=False, print=None)


if __name__ == '__main__':
    main()
