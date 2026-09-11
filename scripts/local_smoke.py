"""Start the actual production entrypoint, exercise HTTP, and verify restart storage.

With a configured key, processes real files. Without one, checks and records the
real controlled MODEL_NOT_CONFIGURED failure. Never substitutes the provider.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile
import aiohttp

ROOT = Path(__file__).resolve().parents[1]


async def wait_ready(session, base):
    for _ in range(60):
        try:
            async with session.get(base + '/api/v1/health') as response:
                if response.status == 200: return await response.json()
        except aiohttp.ClientError: pass
        await asyncio.sleep(.1)
    raise RuntimeError('The application did not become healthy.')


async def run(args):
    out = Path(args.output);out.mkdir(parents=True,exist_ok=True)
    selected = [('Balance Sheet','balance_sheet'),('Profit & Loss','profit_and_loss'),('Cash Flows','cash_flow_statement'),('Invoices','invoice')]
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ,'HOST':'127.0.0.1','PORT':'8125','DATABASE_BACKEND':'sqlite','DATABASE_PATH':str(Path(directory)/'smoke.sqlite3')}
        base = 'http://127.0.0.1:8125'
        def start(): return subprocess.Popen([sys.executable,'-m','backend.app.main'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        process = start()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=540)) as session:
                health = await wait_ready(session,base);checks = {'health':health}
                for route in ['/', '/docs', '/openapi.json', '/static/js/app.js', '/static/css/app.css']:
                    async with session.get(base + route) as response:
                        assert response.status == 200, route
                        checks[route] = response.status
                names=[]
                if args.dataset:
                    with ZipFile(args.dataset) as archive:
                        for folder,kind in selected:
                            member = next(i for i in archive.infolist() if not i.is_dir() and Path(i.filename).parent.name==folder)
                            name=Path(member.filename).name;data=archive.read(member)
                            form=aiohttp.FormData();form.add_field('document_type',kind)
                            form.add_field('file',data,filename=name,content_type='application/pdf' if name.endswith('.pdf') else 'image/jpeg')
                            async with session.post(base+'/api/v1/documents/process',data=form) as response:
                                result=await response.json()
                                expected = 201 if health['model_configured'] else 503
                                assert response.status == expected,(kind,response.status,result.get('error'))
                                (out/(kind+'.json')).write_text(json.dumps({'source':member.filename,'http_status':response.status,'live_model_configured':health['model_configured'],'response':result},indent=2,ensure_ascii=False))
                            names.append(name)
                async with session.get(base+'/api/v1/documents') as response:
                    listing=await response.json();assert listing['total']==len(names)
                process.terminate();process.wait(timeout=5);process=start();await wait_ready(session,base)
                for name in names:
                    async with session.get(base+'/api/v1/documents/'+__import__('urllib.parse',fromlist=['quote']).quote(name,safe='')) as response:
                        assert response.status==200
                checks['persisted_after_process_restart']=len(names)
                checks['live_model_verified']=bool(names) and health['model_configured']
                (out/'smoke_report.json').write_text(json.dumps(checks,indent=2))
                print(json.dumps(checks,indent=2))
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset');parser.add_argument('--output',default='sample_outputs/local_run')
    asyncio.run(run(parser.parse_args()))
