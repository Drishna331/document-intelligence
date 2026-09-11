"""Test-only browser server with a synthetic provider; never a deployment entrypoint."""
import os
from dataclasses import replace
from aiohttp import web
from backend.app.main import create_app
from backend.app.core.config import Settings
from backend.tests.helpers import StubModel

if __name__ == '__main__':
    settings = replace(Settings(), database_path=os.environ['SMOKE_DATABASE_PATH'])
    web.run_app(create_app(settings, model_client=StubModel()), host='127.0.0.1', port=8124, access_log=None)
