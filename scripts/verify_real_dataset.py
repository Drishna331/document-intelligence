"""Run every supported file in a dataset directory through the live API.

This deliberately records failures as received; it never derives success from a
partial response.  Folder names only provide the UI-selected document type.
"""
import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
TYPES = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
CATEGORIES = {'Invoices': 'invoice', 'Balance Sheet': 'balance_sheet',
              'Profit & Loss': 'profit_and_loss', 'Cash Flows': 'cash_flow_statement'}


def root_cause(code, response):
    if code in {'MODEL_UNAVAILABLE', 'MODEL_TIMEOUT', 'MODEL_REQUEST_FAILED'}:
        return 'EXTERNAL_PROVIDER_FAILURE'
    if code in {'OCR_FAILED', 'OCR_TIMEOUT', 'OCR_UNAVAILABLE', 'UNREADABLE_TEXT'}:
        return 'OCR_LIMITATION'
    if code in {'EXTRACTION_EMPTY', 'INVALID_PERIODS', 'EXTRACTION_SCHEMA_ERROR', 'GROUNDING_REJECTED'}:
        return 'SOURCE_DOCUMENT_AMBIGUITY'
    if response and response.get('validation', {}).get('overall_status') == 'NOT_APPLICABLE':
        return 'EXPECTED_NOT_APPLICABLE'
    return 'APPLICATION_BUG' if code else None


def summarize(record):
    response = record.get('response') or record.get('result') or {}
    error = record.get('error') or response.get('error') or {}
    extracted = response.get('extracted_data')
    warnings = (extracted or {}).get('warnings', [])
    return {
        'filename': record['filename'], 'document_type': record['document_type'],
        'file_validation': (response.get('file_validation') or {}).get('status', 'FAILED'),
        'ocr_status': 'PASS' if (response.get('processing_metadata') or {}).get('pages') else 'FAILED',
        'extraction_status': 'PASS' if extracted is not None else 'FAILED',
        'grounding_status': 'FAIL' if any(str(w).startswith('GROUNDING_REJECTED:') for w in warnings) else ('PASS' if extracted else 'FAILED'),
        'financial_validation_status': (response.get('validation') or {}).get('overall_status', 'NOT_APPLICABLE'),
        'processing_status': response.get('processing_status', 'FAILED'),
        'processing_time_ms': (response.get('processing_metadata') or {}).get('processing_time_ms', record['elapsed_ms']),
        'error_failure_reason': error.get('code') or error.get('message'),
        'root_cause': root_cause(error.get('code'), response), 'http_status': record.get('http_status'),
        'persistence_retrieval': record.get('persistence_retrieval', 'FAILED'),
    }


async def main(args):
    dataset, output = Path(args.dataset), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in dataset.rglob('*') if p.is_file() and p.suffix.lower() in TYPES and p.parent.name in CATEGORIES)
    rows = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=args.timeout)) as session:
        for path in files:
            kind = CATEGORIES[path.parent.name]; started = time.monotonic()
            raw = {'filename': path.name, 'document_type': kind}
            try:
                form = aiohttp.FormData(); form.add_field('document_type', kind)
                form.add_field('file', path.read_bytes(), filename=path.name, content_type=TYPES[path.suffix.lower()])
                async with session.post(args.api.rstrip('/') + '/api/v1/documents/process', data=form) as response:
                    raw['http_status'] = response.status; payload = await response.json(); raw.update(response=payload)
                async with session.get(args.api.rstrip('/') + '/api/v1/documents/' + quote(path.name, safe='')) as response:
                    raw['persistence_retrieval'] = 'PASS' if response.status == 200 else 'FAILED'
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                raw['error'] = {'code': 'API_UNAVAILABLE', 'message': type(exc).__name__}
            raw['elapsed_ms'] = round((time.monotonic() - started) * 1000)
            row = summarize(raw); rows.append(row)
            print(row['document_type'], row['filename'], row['http_status'], row['error_failure_reason'], flush=True)
    counts = Counter(r['document_type'] for r in rows)
    totals = {'TOTAL': len(rows), 'Invoices': counts['invoice'], 'Balance Sheets': counts['balance_sheet'], 'P&L': counts['profit_and_loss'], 'Cash Flow': counts['cash_flow_statement'],
              'PASS': sum(r['processing_status'] == 'PASS' for r in rows), 'FAIL': sum(r['financial_validation_status'] == 'FAIL' for r in rows),
              'NOT_APPLICABLE': sum(r['financial_validation_status'] == 'NOT_APPLICABLE' for r in rows),
              'OCR failures': sum(r['ocr_status'] == 'FAILED' for r in rows), 'extraction failures': sum(r['extraction_status'] == 'FAILED' for r in rows),
              'grounding failures': sum(r['grounding_status'] == 'FAIL' for r in rows), 'financial validation failures': sum(r['financial_validation_status'] == 'FAIL' for r in rows),
              'provider failures': sum(r['root_cause'] == 'EXTERNAL_PROVIDER_FAILURE' for r in rows), 'persistence failures': sum(r['persistence_retrieval'] == 'FAILED' for r in rows)}
    (output / 'dataset_verification.json').write_text(json.dumps({'totals': totals, 'documents': rows}, indent=2))
    columns = ['filename','document_type','file_validation','ocr_status','extraction_status','grounding_status','financial_validation_status','processing_status','processing_time_ms','error_failure_reason','root_cause','persistence_retrieval']
    lines = ['# Real Dataset Verification', '', '## Totals', ''] + [f'- {k}: {v}' for k, v in totals.items()] + ['', '## Documents', '', '| ' + ' | '.join(columns) + ' |', '|' + '|'.join(['---'] * len(columns)) + '|']
    lines += ['| ' + ' | '.join(str(r.get(c) or '').replace('|', '/') for c in columns) + ' |' for r in rows]
    (output / 'dataset_verification.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('dataset'); parser.add_argument('--api', required=True); parser.add_argument('--output', default='docs/real_dataset_verification'); parser.add_argument('--timeout', type=int, default=420)
    asyncio.run(main(parser.parse_args()))
