# Verification report

The local implementation is runnable and its automated checks pass. This report
does not certify a completed deployment or measured live LLM extraction quality.
Verification was performed on 11 September 2026 in the supplied workspace.

## Executed checks

| Check | Observed result |
| --- | --- |
| Automated suite | 54 tests passed using `python -m unittest discover -s backend/tests -t . -v`. |
| Real dataset input/OCR | 50 documents, 57 pages/images; 56 OCR pages and 1 native-text page; no processing exceptions. |
| Full dataset OCR elapsed time | 79.639 seconds in this workspace; not a cloud performance guarantee. |
| Real source reference replays | Four categories returned HTTP 201 with applicable financial checks passing. The model was replaced by an explicitly annotated fixture. |
| Actual production entrypoint | Started `python -m backend.app.main`; checked dashboard, health, API docs, schema and static files over HTTP. |
| Actual model-unconfigured behavior | Real uploads of one document per category returned controlled HTTP 503 `MODEL_NOT_CONFIGURED`, with recovered OCR text and stored FAILED results. |
| Process-restart persistence | Stopped and restarted the production process; all four stored results remained retrievable. |
| Static frontend contract | HTML IDs match JavaScript selectors; upload fields and four type options exist; JavaScript syntax checks passed; user values render with textContent. |

The automated suite covers PDF/JPG/PNG validation, three/four-page limits, empty and
corrupt files, MIME/signature mismatch, upload/pixel limits, filename paths and spaces,
native-text bypass, actual PNG/scanned-PDF OCR, number parsing, bracketed negatives,
missing values, tolerance, invoice rules, comparative balance-sheet rules, P&L rules,
cash-flow rules, evidence rejection, malformed model output, provider error contracts,
request timeouts, HTTP processing/get/list/health, latest-result overwrite, database
errors, SQLite persistence and the Turso request/response contract.

Mocked provider and remote-database tests establish application behavior for those
contracts. They do not establish a working live account or external-service connection.

## Source-backed reference samples

| Source | Actual stages exercised | Financial result |
| --- | --- | --- |
| `batch1-1109.jpg` | File validation, real OCR, annotated-response replay, grounding, arithmetic, HTTP and SQLite | 9 PASS; 1 NOT_APPLICABLE |
| `Consolidated Balance Sheet 2025.pdf` | Same stages with comparative 2025/2024 values | 6 PASS |
| `Consolidated Profit & Loss 2025.pdf` | Same stages with comparative 2025/2024 values | 9 PASS; 5 NOT_APPLICABLE |
| `Consolidated Cash Flow Statement 2022.pdf` | Native text, annotated-response replay, grounding, arithmetic, HTTP and SQLite | 4 PASS |

Reference fixtures contain source identifiers and SHA-256 hashes. The replay
script verifies the actual input hash before using a fixture. Their provenance
explicitly says `live_model_invocation: false`. Production services cannot select
the reference provider through environment configuration.

The invoice sample demonstrates decimal commas, net/gross columns and absent
values. The statements exercise comparative columns and signed cash flows. The
P&L source includes an amalgamation adjustment in one period and a dash in another;
the dash is not silently made zero. Synthetic tests additionally demonstrate a
financial FAIL and invalid input.

## Defects found during execution

**Incorrect OCR rotation.** Tesseract OSD suggested 180-degree rotation for three
upright receipts. This reduced text quality. The implementation now compares actual
recognition results and accepts rotation only when quality improves. Mean OCR word
confidence improved from 27.04 to 65.83 for `X51006334741.jpg`, 31.37 to 77.51 for
`X51005719883.jpg`, and 39.34 to 78.87 for `X51005757342.jpg`. These numbers describe
OCR output diagnostics, not measured field accuracy.

**Filename encoding.** The production-process smoke test found that multipart
clients could percent-encode spaces. Decoding before filename sanitization restored
consistent retrieval, and a regression test covers spaces in uploaded filenames.

**Missing adjustment arithmetic.** Explicit but unreadable adjustment rows must
remain required operands. Financial rules retain such operands and return
NOT_APPLICABLE instead of dropping them from the calculation.

## Outstanding verification

| Gate | Why it did not run | Required next action |
| --- | --- | --- |
| Live Gemini extraction | No model API key was configured. | Configure a key, process real documents of all four types, and compare field/table coverage to the originals. |
| Browser interactions and rendering | Playwright was present but the Chromium executable was absent. | Install Chromium and run `node scripts/browser_smoke.mjs`, then exercise the public UI. |
| Docker build | Docker unavailable; package downloads blocked. | Build the Dockerfile in an authorized environment and run the container smoke checks. |
| Live Turso connection | No account URL/token configured. | Configure the hosted database and verify writes/reads across a hosted restart. |
| Public repository | GitHub access was blocked and connector disabled. | Create/push the public repository after reviewing included sample data. |
| Public deployment | Render/Railway connectors disabled; no hosting account access. | Follow `docs/deployment.md`, deploy and record only verified URLs. |

The frontend assets and JavaScript were statically checked and served over HTTP.
No browser screenshot or interactive browser test success is claimed.
