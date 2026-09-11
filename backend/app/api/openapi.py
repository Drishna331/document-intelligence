from ..schemas.document import DocumentResult, DocumentList
from ..schemas.extraction import DocumentType


def specification():
    schemas = {}
    for model in (DocumentResult, DocumentList):
        schema = model.model_json_schema(ref_template='#/components/schemas/{model}')
        schemas.update(schema.pop('$defs', {}))
        schemas[model.__name__] = schema
    schemas['Error'] = {'type': 'object', 'required': ['error', 'processing_status'], 'properties': {
        'error': {'type': 'object', 'required': ['code', 'message'], 'properties': {
            'code': {'type': 'string'}, 'message': {'type': 'string'}, 'request_id': {'type': 'string'},
            'details': {'type': 'object'}}}, 'processing_status': {'type': 'string', 'enum': ['FAILED']},
        'result': {'$ref': '#/components/schemas/DocumentResult'}}}

    def response(name, description='Success'):
        return {'description': description, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + name}}}}

    errors = {str(code): response('Error', 'Controlled error') for code in (400, 404, 413, 415, 422, 429, 500, 502, 503, 504)}
    return {'openapi': '3.1.0', 'info': {'title': 'Document Intelligence API', 'version': '1.0.0',
            'description': 'Page-aware document extraction, evidence, deterministic financial checks and persistent results.'},
        'servers': [{'url': '/'}], 'components': {'schemas': schemas}, 'paths': {
            '/api/v1/health': {'get': {'summary': 'Check server and database health', 'responses': {
                '200': {'description': 'Service online; ready_for_processing reports model and OCR configuration.'}, **errors}}},
            '/api/v1/documents/process': {'post': {'summary': 'Process a PDF, JPG or PNG of up to 3 pages',
                'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {
                    'type': 'object', 'required': ['file', 'document_type'], 'properties': {
                        'file': {'type': 'string', 'format': 'binary'},
                        'document_type': {'type': 'string', 'enum': list(DocumentType.__args__)}}}}}},
                'responses': {'201': response('DocumentResult', 'Processed and persisted, including financial failures'), **errors}}},
            '/api/v1/documents': {'get': {'summary': 'List latest saved results for the dashboard',
                'parameters': [{'name': 'q', 'in': 'query', 'schema': {'type': 'string'}},
                    {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 20}},
                    {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 0, 'default': 0}}],
                'responses': {'200': response('DocumentList'), **errors}}},
            '/api/v1/documents/{document_name}': {'get': {'summary': 'Retrieve the latest result by sanitized document name',
                'parameters': [{'name': 'document_name', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                'responses': {'200': response('DocumentResult'), **errors}}},
        }}
