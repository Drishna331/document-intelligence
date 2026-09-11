'use strict';
const $ = selector => document.querySelector(selector);
const state = {offset: 0, limit: 20, total: 0, maxBytes: 15 * 1024 * 1024, load: 0};
const typeNames = {invoice: 'Invoice', balance_sheet: 'Balance sheet', profit_and_loss: 'Profit and loss', cash_flow_statement: 'Cash flow'};
function el(tag, text, className) {const node = document.createElement(tag); if(text !== undefined) node.textContent = text; if(className) node.className = className; return node;}
function label(key) {return key.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());}
function status(value) {return el('span', value, 'status ' + value.toLowerCase());}
function date(value) {const d = new Date(value); return Number.isNaN(d.valueOf()) ? value : d.toLocaleString();}
async function request(url, options = {}) {
  let response, body;
  try {response = await fetch(url, options); body = await response.json();}
  catch (cause) {if(cause.name === 'AbortError') throw cause; throw new Error('The server could not be reached. Check the connection and try again.');}
  if(!response.ok) {const error = new Error(body.error?.message || 'The request failed.'); error.body = body; throw error;}
  return body;
}
function evidence(value) {
  const container = el('div');
  container.append(el('span', value?.value ?? 'Not present / unreadable', value?.value == null ? 'field-value missing' : 'field-value'));
  if(value?.evidence) {const details = el('details'); details.append(el('summary', 'Evidence · Page ' + value.evidence.page_number), el('blockquote', value.evidence.source_text)); container.append(details);}
  if(value?.reason) container.append(el('div', value.reason, 'reason'));
  return container;
}
function fields(values) {
  const grid = el('div', undefined, 'field-grid');
  for(const [key, value] of Object.entries(values || {})) {const item = el('div', undefined, 'field'); item.append(el('span', label(key), 'field-label'), evidence(value)); grid.append(item);}
  return grid;
}
function table(columns, rows) {
  const wrapper = el('div', undefined, 'table-scroll'), t = el('table'), head = el('thead'), header = el('tr'), body = el('tbody');
  columns.forEach(c => header.append(el('th', c))); head.append(header);
  for(const row of rows) {const tr = el('tr'); for(const item of row) {const td = el('td'); td.append(item instanceof Node ? item : document.createTextNode(item ?? '—')); tr.append(td);} body.append(tr);}
  t.append(head, body); wrapper.append(t); return wrapper;
}
function showResult(result, updateLocation = true) {
  $('#result-title').textContent = result.document_name;
  const content = $('#result-content'); content.replaceChildren();
  const summary = el('div', undefined, 'result-summary'); summary.append(el('span', 'Processing '), status(result.processing_status), el('span', 'Financial checks '), status(result.validation.overall_status)); content.append(summary);
  const meta = result.processing_metadata;
  if(meta.error_message) content.append(el('p', meta.error_message, 'notice error'));
  for(const warning of [...(meta.warnings || []), ...(result.extracted_data?.warnings || [])]) content.append(el('p', warning, 'notice'));
  content.append(el('h3', 'File validation'));
  const fv = result.file_validation;
  content.append(table(['Type', 'Readable', 'Pages', 'Status'], [[fv.file_type || 'Unknown', fv.is_readable ? 'Yes' : 'No', String(fv.page_count ?? 'Unknown'), status(fv.status)]]));
  const data = result.extracted_data;
  if(data) {
    content.append(el('h3', 'Extracted fields'), fields(data.fields));
    for(const period of data.periods) content.append(el('h3', 'Reporting period · ' + period.period), fields(period.fields));
    if(data.line_items.length) {
      content.append(el('h3', 'Line items'));
      const keys = [...new Set(data.line_items.flatMap(item => Object.keys(item.fields)))];
      content.append(table(keys.map(label), data.line_items.map(item => keys.map(key => evidence(item.fields[key])))));
    }
    for(const t of data.tables) {content.append(el('h3', t.title || 'Financial table'), table(['Source label', ...t.columns], t.rows.map(row => [el('span', row.label), ...t.columns.map(c => evidence(row.cells[c]))])));}
  } else content.append(el('p', 'Structured extraction did not complete. The processing error and any recovered source text are shown below.', 'muted'));
  content.append(el('h3', 'Financial validation'));
  if(result.validation.checks.length) content.append(table(['Check / formula', 'Inputs', 'Calculated', 'Reported', 'Variance', 'Status'], result.validation.checks.map(check => {
    const name = el('div', (check.period ? check.period + ' · ' : '') + label(check.name)); name.append(el('small', check.formula));
    if(check.reason) name.append(el('div', check.reason, 'reason'));
    const inputs = el('div'); for(const [key, value] of Object.entries(check.operands)) inputs.append(el('div', `${label(key)}: ${value ?? 'Missing'}`));
    return [name, inputs, check.calculated_value, check.reported_value, check.variance, status(check.status)];
  }))); else content.append(el('p', 'No checks ran because structured extraction did not complete.', 'muted'));
  content.append(el('h3', 'Processing details'));
  const info = el('div', undefined, 'metadata');
  for(const text of [typeNames[result.document_type], date(meta.processed_at), `${(meta.processing_time_ms / 1000).toFixed(2)} seconds`, meta.ocr_used ? 'OCR used' : 'Native text / no OCR', 'Request ' + meta.request_id]) info.append(el('span', text));
  content.append(info);
  for(const page of meta.pages) {const d = el('details'); d.append(el('summary', `Source text · Page ${page.page_number} · ${page.method}`), el('pre', page.text)); content.append(d);}
  const raw = el('details'); raw.id = 'raw-json'; raw.append(el('summary', 'Raw structured JSON'), el('pre', JSON.stringify(result, null, 2))); content.append(raw);
  $('#result').hidden = false; $('#result').focus({preventScroll: true}); $('#result').scrollIntoView({behavior:'auto',block:'start'});
  if(updateLocation) history.replaceState(null, '', '/results?name=' + encodeURIComponent(result.document_name));
}
async function openResult(name) {
  try {showResult(await request('/api/v1/documents/' + encodeURIComponent(name)));}
  catch(error) {$('#list-error').textContent = error.message;}
}
async function loadDocuments() {
  const ticket = ++state.load;
  $('#list-error').textContent = '';
  try {
    const result = await request(`/api/v1/documents?limit=${state.limit}&offset=${state.offset}&q=${encodeURIComponent($('#search').value)}`);
    if(ticket !== state.load) return;
    state.total = result.total; $('#document-count').textContent = `${result.total} saved document${result.total === 1 ? '' : 's'} · Latest result per filename`;
    const rows = $('#document-rows'); rows.replaceChildren();
    for(const doc of result.documents) {
      const row = el('tr'); for(const value of [doc.document_name, typeNames[doc.document_type], status(doc.processing_status), status(doc.validation_status), date(doc.processed_at)]) {const td = el('td'); td.append(value instanceof Node ? value : document.createTextNode(value)); row.append(td);}
      const action = el('td'), button = el('button', 'View result', 'secondary'); button.type = 'button'; button.addEventListener('click', () => openResult(doc.document_name)); action.append(button); row.append(action); rows.append(row);
    }
    if(!result.documents.length) {const tr = el('tr'), td = el('td', 'No processed documents found. Upload a document to begin.', 'empty'); td.colSpan = 6; tr.append(td); rows.append(tr);}
    $('#previous').disabled = state.offset === 0; $('#next').disabled = state.offset + state.limit >= state.total;
    $('#page-info').textContent = state.total ? `${state.offset + 1}–${Math.min(state.offset + state.limit, state.total)} of ${state.total}` : '0 documents';
  } catch(error) {$('#list-error').textContent = error.message; $('#document-count').textContent = 'Saved documents could not be loaded.';}
}
$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const file = $('#document-file').files[0], message = $('#upload-message'); message.className = '';
  if(!file) return;
  if(!/\.(pdf|jpe?g|png)$/i.test(file.name)) {message.textContent = 'Only PDF, JPG and PNG files are supported.'; message.className = 'error'; return;}
  if(!file.size || file.size > state.maxBytes) {message.textContent = file.size ? 'This file exceeds the upload size limit.' : 'The selected file is empty.'; message.className = 'error'; return;}
  $('#process-button').disabled = true; $('#process-button').textContent = 'Processing…';
  message.textContent = 'Reading the document and checking extracted values. Scans may take a few minutes.';
  try {
    const result = await request('/api/v1/documents/process', {method:'POST',body:new FormData($('#upload-form'))});
    showResult(result); message.textContent = result.processing_status === 'PASS' ? 'Document processed and saved.' : 'Document saved. Review the failed or unavailable checks below.';
  } catch(error) {message.textContent = error.message; message.className = 'error'; if(error.body?.result) showResult(error.body.result);}
  finally {$('#process-button').disabled = false; $('#process-button').textContent = 'Process document'; state.offset = 0; await loadDocuments();}
});
$('#refresh').addEventListener('click', loadDocuments);
$('#previous').addEventListener('click', () => {state.offset = Math.max(0, state.offset - state.limit); loadDocuments();});
$('#next').addEventListener('click', () => {state.offset += state.limit; loadDocuments();});
let searchTimer; $('#search').addEventListener('input', () => {clearTimeout(searchTimer); searchTimer = setTimeout(() => {state.offset = 0; loadDocuments();}, 200);});
$('#close-result').addEventListener('click', () => {$('#result').hidden = true; history.replaceState(null, '', '/');});
async function start() {
  try {const health = await request('/api/v1/health'); state.maxBytes = health.max_upload_bytes; $('#service-status').textContent = health.ready_for_processing ? 'Ready to process documents.' : 'The service is online, but document processing needs server configuration. Uploaded documents will show a clear error until it is ready.'; $('#service-status').className = 'notice' + (health.ready_for_processing ? ' ready' : '');}
  catch(error) {$('#service-status').textContent = error.message;}
  await loadDocuments(); const name = new URLSearchParams(location.search).get('name'); if(name) await openResult(name);
}
start();
