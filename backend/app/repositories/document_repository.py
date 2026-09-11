from ..core.errors import AppError
from ..schemas.document import DocumentResult, DocumentSummary, DocumentList


class DocumentRepository:
    def __init__(self, database):
        self.database = database

    async def save(self, result):
        await self.database.execute('''INSERT INTO documents
            (document_name, document_type, processing_status, validation_status, processed_at, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_name) DO UPDATE SET document_type=excluded.document_type,
            processing_status=excluded.processing_status, validation_status=excluded.validation_status,
            processed_at=excluded.processed_at, result_json=excluded.result_json''',
            (result.document_name, result.document_type, result.processing_status, result.validation.overall_status,
             result.processing_metadata.processed_at, result.model_dump_json()))

    async def get(self, name):
        rows = await self.database.execute('SELECT result_json FROM documents WHERE document_name = ?', (name,))
        if not rows:
            raise AppError('DOCUMENT_NOT_FOUND', 'No processed document was found with that name.', 404)
        try:
            return DocumentResult.model_validate_json(rows[0]['result_json'])
        except ValueError:
            raise AppError('STORED_RESULT_INVALID', 'The stored document result is invalid.', 500) from None

    async def list(self, limit, offset, search=''):
        # instr is literal substring search: no wildcard interpretation of user input.
        where = ' WHERE instr(lower(document_name), lower(?)) > 0'
        rows = await self.database.execute('SELECT document_name, document_type, processing_status, validation_status, processed_at FROM documents' +
            where + ' ORDER BY processed_at DESC, document_name LIMIT ? OFFSET ?', (search, limit, offset))
        count = await self.database.execute('SELECT count(*) AS total FROM documents' + where, (search,))
        return DocumentList(documents=[DocumentSummary(**row) for row in rows], limit=limit, offset=offset, total=int(count[0]['total']))
