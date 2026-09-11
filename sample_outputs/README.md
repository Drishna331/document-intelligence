# Sample output provenance

These directories deliberately distinguish executed work from provider-dependent
work that could not be run in this workspace.

| Directory | What actually ran | What it does not prove |
| --- | --- | --- |
| `ocr_run` | Real validation and local OCR/native extraction on all 50 supplied documents. | Semantic extraction accuracy or field completeness. |
| `local_run` | Production HTTP entrypoint, real OCR on one source of each type, controlled missing-model errors, get/list and process-restart persistence. | Successful live Gemini extraction. |
| `reference_runs` | Actual source files, OCR, Pydantic grounding, deterministic financial checks and API persistence, with the model replaced by annotated source-backed fixtures. | Live Gemini compatibility, extraction quality or generalization. |

Reference outputs explicitly identify fixture replay in their provenance and
model metadata. They are not served by any production fallback. The application's
model client never reads `backend/tests/fixtures` or `sample_outputs`.

The reference invoice includes absent discount and other missing metadata as null where the
source lacks it, and source-grounded decimal-comma line items. Statement examples
retain comparative periods and negative values. Synthetic tests separately create
an inconsistent invoice total to verify a real FAIL outcome. No dataset-specific
answers are hardcoded into application services.

Generate live-provider outputs using `scripts/evaluate_dataset.py --api` after
configuring and verifying your own model key. The original dataset is provided
separately and is not duplicated in the source archive.
