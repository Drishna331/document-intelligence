from typing import Literal
from pydantic import Field
from .extraction import StrictModel, DocumentType, ExtractedData, SourcePage

CheckStatus = Literal['PASS', 'FAIL', 'NOT_APPLICABLE']


class FileValidation(StrictModel):
    file_name: str
    file_type: str | None = None
    is_supported: bool = False
    is_readable: bool = False
    page_count: int | None = None
    status: Literal['PASS', 'FAILED'] = 'FAILED'


class Check(StrictModel):
    name: str
    period: str | None = None
    formula: str
    operands: dict[str, str | None]
    calculated_value: str | None
    reported_value: str | None
    variance: str | None
    tolerance: str
    status: CheckStatus
    reason: str | None = None


class Validation(StrictModel):
    checks: list[Check] = Field(default_factory=list)
    overall_status: CheckStatus = 'NOT_APPLICABLE'
    issues: list[str] = Field(default_factory=list)


class Metadata(StrictModel):
    request_id: str
    processed_at: str
    processing_time_ms: int
    ocr_used: bool = False
    model: str | None = None
    extraction_completed: bool = False
    source_sha256: str
    pages: list[SourcePage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class DocumentResult(StrictModel):
    document_name: str
    document_type: DocumentType
    processing_status: Literal['PASS', 'FAILED']
    file_validation: FileValidation
    extracted_data: ExtractedData | None
    validation: Validation
    processing_metadata: Metadata


class DocumentSummary(StrictModel):
    document_name: str
    document_type: DocumentType
    processing_status: Literal['PASS', 'FAILED']
    validation_status: CheckStatus
    processed_at: str


class DocumentList(StrictModel):
    documents: list[DocumentSummary]
    limit: int
    offset: int
    total: int
