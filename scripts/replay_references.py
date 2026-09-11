"""Replay annotated reference responses through the real API for regression checks.

This explicitly substitutes the model. It is NOT a live LLM benchmark and is
never imported by the production application. Actual source files and OCR are
used; changed file hashes stop the replay rather than reusing the wrong answer.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile
import aiohttp
from aiohttp.test_utils import TestServer, TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.main import create_app
from backend.app.core.config import Settings


async def run(dataset, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    records = []
    with ZipFile(dataset) as archive, tempfile.TemporaryDirectory() as directory:
        for path in sorted((ROOT / 'backend/tests/fixtures').glob('*.json')):
            fixture = json.loads(path.read_text()); provenance = fixture['provenance']
            source = archive.read(provenance['source'])
            if hashlib.sha256(source).hexdigest() != provenance['sha256']:
                raise ValueError('The reference document hash does not match.')
            class ReferenceModel:
                async def generate(self, prompt): return json.dumps(fixture['wire_output'])
            settings = replace(Settings(), database_path=str(Path(directory) / 'reference.sqlite3'), llm_model='reference-fixture-replay')
            async with TestClient(TestServer(create_app(settings, model_client=ReferenceModel()))) as client:
                form = aiohttp.FormData(); form.add_field('document_type', path.stem)
                name = Path(provenance['source']).name
                form.add_field('file', source, filename=name, content_type='application/pdf' if name.endswith('.pdf') else 'image/jpeg')
                response = await client.post('/api/v1/documents/process', data=form)
                body = await response.json()
                record = {'provenance': {**provenance, 'model_replaced_by_fixture': True,
                          'api_and_ocr_executed': True}, 'http_status': response.status, 'result': body}
                (output / path.name).write_text(json.dumps(record, indent=2, ensure_ascii=False))
                actual = body.get('validation', {}).get('overall_status', body.get('error', {}).get('code'))
                print(path.stem, response.status, actual, flush=True)
                records.append({'document_type':path.stem,'http_status':response.status,'validation_status':actual})
    (output / 'manifest.json').write_text(json.dumps({'mode':'reference_fixture_replay', 'live_model_invocation':False, 'records':records},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('dataset')
    parser.add_argument('--output',default='sample_outputs/reference_runs')
    args = parser.parse_args();asyncio.run(run(args.dataset,args.output))
