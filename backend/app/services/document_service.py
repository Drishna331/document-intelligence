import asyncio
import hashlib
import time
from datetime import datetime, timezone
from ..core.errors import AppError
from ..core.logging import event
from ..schemas.document import DocumentResult, FileValidation, Validation, Metadata
from .document_validation_service import validate_file, sanitize_filename


class DocumentService:
    def __init__(self, settings, ocr, extraction, financial, repository):
        self.settings, self.ocr, self.extraction = settings, ocr, extraction
        self.financial, self.repository = financial, repository

    async def process(self, data, filename, mime, document_type, request_id):
        start = time.monotonic()
        filename = sanitize_filename(filename)
        metadata = Metadata(request_id=request_id, processed_at=datetime.now(timezone.utc).isoformat(),
                            processing_time_ms=0, source_sha256=hashlib.sha256(data).hexdigest())
        result = DocumentResult(document_name=filename, document_type=document_type, processing_status='FAILED',
            file_validation=FileValidation(file_name=filename), extracted_data=None,
            validation=Validation(), processing_metadata=metadata)
        failure = None
        try:
            event('file_validation_start', request_id, document_name=filename, document_type=document_type)
            result.file_validation = await asyncio.to_thread(validate_file, data, filename, mime, self.settings)
            event('file_validation_complete', request_id, page_count=result.file_validation.page_count)
            event('ocr_start', request_id)
            metadata.pages = await asyncio.to_thread(self.ocr.extract, data, result.file_validation.file_type)
            metadata.ocr_used = any(p.method == 'tesseract' for p in metadata.pages)
            for page in metadata.pages:
                if not page.text.strip():
                    metadata.warnings.append(f'Page {page.page_number} has no readable text.')
                if page.ocr_mean_word_confidence is not None and page.ocr_mean_word_confidence < 80:
                    metadata.warnings.append(f'Page {page.page_number} has low OCR word confidence; review against the original.')
            event('ocr_complete', request_id, ocr_used=metadata.ocr_used, text_characters=sum(len(p.text) for p in metadata.pages))
            event('extraction_start', request_id)
            result.extracted_data = await self.extraction.extract(document_type, metadata.pages)
            metadata.model = self.settings.llm_model
            metadata.extraction_completed = True
            event('extraction_complete', request_id)
            event('financial_validation_start', request_id)
            result.validation = self.financial.validate(document_type, result.extracted_data)
            grounded_rejections = any(w.startswith('GROUNDING_REJECTED:') for w in result.extracted_data.warnings)
            # OCR confidence is advisory.  A value may be independently grounded
            # against the source text even when Tesseract assigns a low confidence;
            # do not turn such a completed, valid document into a false failure.
            low_ocr = any(p.ocr_mean_word_confidence is not None and p.ocr_mean_word_confidence < 50 for p in metadata.pages)
            blank_page = any(not p.text.strip() for p in metadata.pages)
            if result.validation.overall_status == 'PASS' and not grounded_rejections and not blank_page:
                result.processing_status = 'PASS'
            elif result.validation.overall_status == 'NOT_APPLICABLE':
                metadata.warnings.append('Extraction completed, but no financial check could be evaluated. Review is required.')
            if grounded_rejections:
                metadata.warnings.append('Some model values were rejected because their evidence could not be verified.')
            if low_ocr:
                metadata.warnings.append('Low OCR confidence; review the grounded source evidence before relying on the result.')
            if blank_page:
                metadata.warnings.append('A page has no usable source text; review or rescan the document.')
            event('financial_validation_complete', request_id, status=result.validation.overall_status)
        except AppError as exc:
            failure = exc
            if exc.details and 'file_validation' in exc.details:
                result.file_validation = FileValidation.model_validate(exc.details['file_validation'])
            metadata.error_code, metadata.error_message = exc.code, exc.message
            event('processing_failure', request_id, error_code=exc.code)
        except Exception as exc:
            failure = AppError('PROCESSING_FAILED', 'An unexpected processing error occurred.', 500)
            metadata.error_code, metadata.error_message = failure.code, failure.message
            event('processing_failure', request_id, error_code=failure.code, exception_type=type(exc).__name__)
        metadata.processing_time_ms = round((time.monotonic() - start) * 1000)
        metadata.processed_at = datetime.now(timezone.utc).isoformat()
        event('database_save_start', request_id)
        await self.repository.save(result)
        event('database_save_complete', request_id)
        if failure:
            failure.result = result
            raise failure
        event('processing_complete', request_id, status=result.processing_status, processing_time_ms=metadata.processing_time_ms)
        return result
