"""Run actual files through validation/OCR and optionally the full HTTP API.

No answers or filename-specific extraction logic are stored here. Folder labels
only supply the user-selected document type required by the assessment.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from zipfile import ZipFile
import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.services.document_validation_service import validate_file, TYPES
from backend.app.services.ocr_service import OCRService

CATEGORIES = {'Balance Sheet':'balance_sheet', 'Profit & Loss':'profit_and_loss', 'Cash Flows':'cash_flow_statement', 'Invoices':'invoice'}


async def evaluate(args):
    settings, ocr = Settings.from_env(), OCRService(Settings.from_env())
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    records, used = [], {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=400)) as session:
        with ZipFile(args.dataset) as archive:
            for info in archive.infolist():
                if info.is_dir(): continue
                path = Path(info.filename)
                category = CATEGORIES.get(path.parent.name)
                if not category or path.suffix.lower() not in TYPES: continue
                if args.per_category and used.get(category, 0) >= args.per_category: continue
                if info.file_size > settings.max_upload_bytes: continue
                used[category] = used.get(category, 0) + 1
                start = time.monotonic(); data = archive.read(info)
                record = {'source': info.filename, 'document_type': category, 'sha256':hashlib.sha256(data).hexdigest()}
                try:
                    if args.api:
                        form = aiohttp.FormData(); form.add_field('document_type', category)
                        form.add_field('file', data, filename=path.name, content_type=TYPES[path.suffix.lower()])
                        async with session.post(args.api.rstrip('/') + '/api/v1/documents/process', data=form) as response:
                            record['http_status'] = response.status
                            record['response'] = await response.json()
                    else:
                        record['file_validation'] = validate_file(data, path.name, TYPES[path.suffix.lower()], settings).model_dump()
                        record['pages'] = [p.model_dump() for p in ocr.extract(data, TYPES[path.suffix.lower()])]
                except AppError as exc:
                    record['error'] = {'code': exc.code, 'message': exc.message}
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    record['error'] = {'code':'API_UNAVAILABLE', 'message':'API request failed or timed out.'}
                record['elapsed_seconds'] = round(time.monotonic() - start, 3)
                filename = f'{category}_{used[category]:02d}.json'
                (output / filename).write_text(json.dumps(record, ensure_ascii=False, indent=2))
                records.append({k:v for k,v in record.items() if k not in ('pages','response')})
                print(category, path.name, record.get('http_status', 'OCR'), record['elapsed_seconds'], flush=True)
    (output / 'manifest.json').write_text(json.dumps({'mode':'api' if args.api else 'ocr', 'records':records}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset'); parser.add_argument('--output', default='sample_outputs/live_run')
    parser.add_argument('--api', help='API base URL; omit for OCR-only inspection')
    parser.add_argument('--per-category', type=int, default=0, help='0 means all documents')
    asyncio.run(evaluate(parser.parse_args()))
