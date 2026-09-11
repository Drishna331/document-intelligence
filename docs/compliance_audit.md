# Case study compliance audit

This checklist compares the delivered implementation to the official supplied
case study and the user's expanded build instructions. “Tested” means executed
here; fixture tests and static checks are identified explicitly. No evaluation
score is estimated because live extraction quality and deployment have not been measured.

The submission is **not yet ready to claim full case-study completion**. The code,
local tests, OCR records and supporting materials are delivered. Live model
verification, browser testing, hosted persistence, container build, public GitHub
and verified deployment URLs remain required.

| Requirement | Implemented | Tested here | Evidence or remaining condition |
| --- | --- | --- | --- |
| PDF input | Yes | Yes | validation service; unit tests; 30 real PDFs |
| JPG input | Yes | Yes | 20 real invoice images |
| PNG input | Yes | Yes | Generated PNG validation and real OCR integration |
| Empty upload rejection | Yes | Yes | test_validation.py |
| Corrupt PDF/image rejection | Yes | Yes | File integrity and signature tests |
| Unsupported formats rejected | Yes | Yes | Validation and HTTP 415 test |
| MIME and extension checks | Yes | Yes | Spoofed-MIME/signature tests |
| Up to three pages | Yes | Yes | Three accepted; four rejected |
| Safe size/pixel limits | Yes | Yes | Bounded upload and rendering checks |
| Encrypted PDF rejection | Yes | Code inspected | Password-protected inputs are rejected |
| Native PDF text extraction | Yes | Yes | 2022 cash flow and synthetic native PDF |
| Scanned PDF OCR fallback | Yes | Yes | 29 scanned PDFs plus generated scanned-PDF test |
| Image OCR | Yes | Yes | Real invoices and generated PNG |
| Page boundaries preserved | Yes | Yes | SourcePage models and multi-page cash-flow records |
| Orientation handling | Yes | Real dataset rerun | Incorrect OSD rotations corrected by comparing OCR quality |
| Invoice structured extraction | Yes | Annotated replay only | Live Gemini extraction outstanding |
| Balance-sheet structured extraction | Yes | Annotated replay only | Live Gemini extraction outstanding |
| P&L structured extraction | Yes | Annotated replay only | Live Gemini extraction outstanding |
| Cash-flow structured extraction | Yes | Annotated replay only | Live Gemini extraction outstanding |
| All meaningful fields | Designed for this | Not established live | Extensible schema and prompt; needs source-level coverage evaluation |
| All table/line-item values | Designed for this | Reference tables only | Completeness depends on OCR and model output |
| Comparative period association | Yes | Reference and unit tests | Separate period objects; duplicate/unknown periods rejected |
| Missing values as null | Yes | Yes | Grounding/minimum-key tests and reference outputs |
| No invented unsupported values | Safeguards implemented | Rejection tests | Exact-text grounding cannot prove semantic correctness or correct OCR |
| Evidence and page references | Yes | Yes | Wrong-page and fake-evidence rejection tests |
| Explainable confidence if used | OCR diagnostic only | Yes | No LLM confidence score; documented mean-word diagnostic |
| Pydantic structured validation | Yes | Yes | Strict wire models and response models |
| Deterministic financial checks | Yes | Yes | Decimal-based service; no LLM arithmetic |
| Numerical tolerance | Yes | Yes | Absolute 0.05 in displayed units; boundary tests |
| Negative/bracketed number parsing | Yes | Yes | Unit tests and actual cash-flow values |
| Missing operands NOT_APPLICABLE | Yes | Yes | No default-zero behavior |
| Invoice checks and tax basis | Yes | Yes | Unit tests; 9 passing reference checks |
| Balance equation and components | Yes | Yes | Comparative unit tests; 6 reference checks |
| P&L required checks | Yes | Yes | Unit tests; reference run; general missing fields remain N/A |
| Cash-flow checks per period | Yes | Yes | Unit tests; 4 reference checks |
| Processing PASS / FAILED | Yes | Yes | Financial failure and missing-provider API tests |
| Stable response fields | Yes | Yes | DocumentResult schema and HTTP assertions |
| POST multipart process endpoint | Yes | Real HTTP, provider mocked or absent | Production route and reference/test runs |
| GET by document name | Yes | Yes | Filename decoding regression and actual restart smoke |
| Latest result on repeated filename | Yes | Yes | Upsert and repeated-upload tests |
| Processed-document list API | Yes | Yes | Search, pagination and database-backed list tests |
| Health endpoint | Yes | Yes | Standalone HTTP and unit tests |
| OpenAPI documentation | Yes | HTTP/schema tests | `/openapi.json` generated from response models |
| Swagger UI | Yes | Asset page only | CDN interface requires a browser check |
| Correct HTTP/error envelopes | Yes | Yes | Invalid type/form, provider, database and exception tests |
| SQLite persistence | Yes | Actual process restart | Four stored results retrieved after restart |
| Hosted persistent store | Turso adapter | Mocked protocol only | Live credentials and restart verification required |
| Upload/type-selection frontend | Yes | Static/HTTP checks only | Browser test provided, Chromium unavailable |
| Database-connected dashboard | Yes | API/static checks only | Browser interaction outstanding |
| Fields, tables and evidence UI | Yes | Static checks only | Browser rendering outstanding |
| Financial/missing-value indicators | Yes | Static checks only | PASS/FAIL/N/A and missing-value render paths |
| Expandable raw JSON | Yes | Static checks only | Browser interaction outstanding |
| Responsive UI | CSS implemented | Not visually verified | Browser smoke includes a mobile-width check |
| Modular architecture | Yes | Inspected | Separate routes, schemas, services, repository and core |
| Structured stage logs | Yes | Observed in tests | Request IDs, stage names and controlled codes |
| Graceful OCR/model/DB failures | Yes | Tests and real missing-key runs | No exception payloads returned to users |
| Secret environment configuration | Yes | Inspected | .env.example; .env ignored; no real keys supplied |
| Safe filename/temp handling | Yes | Filename tests and OCR runs | No uploaded source path is opened directly |
| Automated tests | Yes | 54 passing | Standard-library unittest, HTTP and real OCR tests |
| Real sample JSON outputs | OCR and failed API outputs | Yes | All 50 OCR records and four actual missing-key API responses |
| Successful AI sample outputs | Reference replays only | Not live | Explicitly labelled; replace with verified live outputs before final submission |
| Validation failure/missing scenario | Yes | Yes | Synthetic financial FAIL; source missing fields and missing-model cases |
| README and setup instructions | Yes | Commands used where available | README.md |
| Architecture diagram | Yes | Rendered artifact | docs/architecture.png; editable diagram in PPTX |
| Solution presentation | Yes | Package/render QA | docs/solution_presentation.pptx and PDF |
| AI tool declaration | Yes | Included | README and presentation |
| Limitations/production improvements | Yes | Included | README, verification report and slides |
| Deployment configuration | Yes | Static review only | Dockerfile, compose.yaml, render.yaml |
| Container build/start | Prepared | Not executed | Docker and package access unavailable |
| Public GitHub source | No | No | Requires authorized repository creation/push |
| Live frontend/backend URLs | No | No | Requires hosting deployment and verification |
| Live Swagger/health URLs | No | No | Cannot exist until verified deployment |
| Interview walkthrough | Prepared | Not performed | Presentation and README demo sequence |

## Completion gates

1. Run the browser smoke and container build in an environment with their dependencies.
2. Configure a model key and quantify real extraction coverage for all document types.
3. Verify the live Turso integration and persistence across a hosted restart.
4. Publish the reviewed source, deploy the application and test all public endpoints.
5. Replace the README's explicit “not deployed” status with the actual verified URLs
   and record real-provider sample results before presenting the submission as complete.
