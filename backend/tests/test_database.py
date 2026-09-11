import unittest
from dataclasses import replace
from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.core.errors import AppError


class Response:
    status=200
    def __init__(self,payload): self.payload=payload
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def json(self):return self.payload


class Transport:
    def __init__(self,payload):self.payload=payload;self.request=None
    def post(self,url,**kwargs):self.request=(url,kwargs);return Response(self.payload)


class TursoContractTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return replace(Settings(),database_backend='turso',turso_database_url='libsql://unit-test.turso.io',turso_auth_token='unit-test-token')

    async def test_bound_sql_arguments_and_result_decoding(self):
        transport=Transport({'results':[{'type':'ok','response':{'result':{'cols':[{'name':'total'}],'rows':[[{'type':'integer','value':'4'}]]}}}]})
        result=await Database(self.settings(),transport).execute('SELECT count(*) AS total FROM documents WHERE document_name = ?',("a' OR 1=1 --",))
        self.assertEqual(result,[{'total':'4'}])
        url,kwargs=transport.request
        self.assertEqual(url,'https://unit-test.turso.io/v2/pipeline')
        self.assertEqual(kwargs['json']['requests'][0]['stmt']['args'],[{'type':'text','value':"a' OR 1=1 --"}])

    async def test_remote_sql_error_is_controlled(self):
        transport=Transport({'results':[{'type':'error','error':{'message':'private database details'}}]})
        with self.assertRaises(AppError) as ctx: await Database(self.settings(),transport).execute('SELECT 1')
        self.assertNotIn('private',ctx.exception.message)
