// Requires Playwright and its Chromium browser. Uses a separate synthetic test server.
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = path.dirname(path.dirname(new URL(import.meta.url).pathname));
const work = await fs.mkdtemp(path.join(os.tmpdir(), 'docintel-browser-'));
const python = process.env.PYTHON || 'python';
const server = spawn(python, ['-m','backend.tests.smoke_server'], {cwd:root,
  env:{...process.env,SMOKE_DATABASE_PATH:path.join(work,'browser.sqlite3')}, stdio:'ignore'});
let browser;
try {
  let ready=false;
  for(let i=0;i<40;i++){try{const r=await fetch('http://127.0.0.1:8124/api/v1/health'); if(r.ok){ready=true;break;}}catch{} await new Promise(r=>setTimeout(r,100));}
  assert(ready,'Test server failed to start');
  await new Promise((resolve,reject)=>{const p=spawn(python,['-c', 'from backend.tests.helpers import pdf_bytes; from pathlib import Path; Path("'+path.join(work,'invoice.pdf')+'").write_bytes(pdf_bytes())'],{cwd:root});p.on('exit',c=>c?reject(Error('Fixture generation failed')):resolve());});
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8124/');
  await page.locator('#document-file').setInputFiles(path.join(work,'invoice.pdf'));
  await page.locator('#process-button').click();
  await page.locator('#result-title').filter({hasText:'invoice.pdf'}).waitFor();
  assert((await page.locator('#result-content').innerText()).includes('110.00'));
  await page.locator('#raw-json summary').click();
  assert((await page.locator('#raw-json pre').innerText()).includes('"processing_status": "PASS"'));
  await page.reload();await page.locator('#result-title').filter({hasText:'invoice.pdf'}).waitFor();
  await page.locator('#search').fill('does-not-exist');
  await page.getByText('No processed documents found. Upload a document to begin.').waitFor();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  assert.deepEqual(errors,[]);
  await fs.mkdir(path.join(root,'test-results'),{recursive:true});
  await page.screenshot({path:path.join(root,'test-results/mobile.png'),fullPage:true});
  console.log('Browser smoke passed: upload, result, raw JSON, reload persistence, search and mobile width.');
} finally {if(browser)await browser.close();server.kill();await fs.rm(work,{recursive:true,force:true});}
