"""SQLite locally; the same SQL over Turso HTTP for ephemeral hosting."""
import asyncio
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
import aiohttp
from .errors import AppError

CREATE_TABLE = '''CREATE TABLE IF NOT EXISTS documents (
    document_name TEXT PRIMARY KEY,
    document_type TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    result_json TEXT NOT NULL
)'''


class Database:
    def __init__(self, settings, session):
        self.settings, self.session = settings, session

    async def initialize(self):
        if self.settings.database_backend == 'sqlite':
            await asyncio.to_thread(Path(self.settings.database_path).parent.mkdir, parents=True, exist_ok=True)
        await self.execute(CREATE_TABLE)
        await self.execute('CREATE INDEX IF NOT EXISTS documents_processed_at ON documents(processed_at DESC)')

    def _sqlite(self, sql, args):
        with sqlite3.connect(self.settings.database_path, timeout=15) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA journal_mode=WAL')
            cursor = connection.execute(sql, args)
            return [dict(row) for row in cursor.fetchall()]

    async def execute(self, sql, args=()):
        try:
            if self.settings.database_backend == 'sqlite':
                return await asyncio.to_thread(self._sqlite, sql, args)
            url = self.settings.turso_database_url.replace('libsql://', 'https://').rstrip('/')
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise AppError('DATABASE_CONFIGURATION_ERROR', 'The database configuration is invalid.', 503)
            encoded = [{'type': 'integer' if isinstance(v, int) else 'text', 'value': str(v)} for v in args]
            payload = {'requests': [{'type': 'execute', 'stmt': {'sql': sql, 'args': encoded}}, {'type': 'close'}]}
            async with self.session.post(url + '/v2/pipeline', json=payload,
                    headers={'Authorization': 'Bearer ' + self.settings.turso_auth_token},
                    timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status != 200:
                    raise AppError('DATABASE_UNAVAILABLE', 'The document database is unavailable.', 503)
                body = await response.json()
            result = body['results'][0]
            if result['type'] != 'ok':
                raise AppError('DATABASE_ERROR', 'The database operation could not be completed.', 503)
            table = result['response']['result']
            return [{column['name']: cell.get('value') for column, cell in zip(table['cols'], row)} for row in table['rows']]
        except AppError:
            raise
        except (sqlite3.Error, aiohttp.ClientError, asyncio.TimeoutError, KeyError, TypeError, ValueError, OSError):
            raise AppError('DATABASE_ERROR', 'The document database could not complete the request.', 503) from None
