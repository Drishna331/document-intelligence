import io
import re
import warnings
from pathlib import PurePosixPath
import fitz
from PIL import Image
from ..core.errors import AppError
from ..schemas.document import FileValidation

TYPES = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}


def sanitize_filename(name):
    name = PurePosixPath((name or 'document').replace('\\', '/')).name
    name = re.sub(r'[^\w .()&+-]', '_', name, flags=re.UNICODE).strip(' .')
    if not name:
        name = 'document'
    if len(name) > 180:
        suffix = PurePosixPath(name).suffix
        name = name[:180 - len(suffix)] + suffix
    return name


def validate_file(data, filename, mime, settings):
    filename = sanitize_filename(filename)
    extension = PurePosixPath(filename).suffix.lower()
    expected = TYPES.get(extension)
    result = FileValidation(file_name=filename, file_type=expected)

    def fail(code, message, status=400):
        raise AppError(code, message, status, {'file_validation': result.model_dump()})

    if not expected:
        fail('UNSUPPORTED_FILE_TYPE', 'Only PDF / JPG / PNG documents are supported.', 415)
    result.is_supported = True
    if not data:
        fail('EMPTY_FILE', 'The uploaded file is empty.')
    if len(data) > settings.max_upload_bytes:
        fail('FILE_TOO_LARGE', 'The upload exceeds the configured file size limit.', 413)
    supplied = (mime or '').split(';', 1)[0].strip().lower()
    if supplied not in ('', 'application/octet-stream', expected):
        fail('MIME_MISMATCH', 'The declared file type does not match the filename.', 415)
    signature = ('application/pdf' if data.startswith(b'%PDF-') else
                 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else
                 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else None)
    if signature != expected:
        fail('INVALID_FILE_SIGNATURE', 'The file contents do not match a readable PDF / JPG / PNG.')
    try:
        if expected == 'application/pdf':
            if b'%%EOF' not in data[-2048:]:
                fail('CORRUPTED_FILE', 'The PDF is incomplete or corrupted.')
            with fitz.open(stream=data, filetype='pdf') as doc:
                if doc.needs_pass:
                    fail('ENCRYPTED_PDF', 'Password-protected PDFs are not supported.')
                result.page_count = len(doc)
                if not 0 < len(doc) <= settings.max_pages:
                    fail('PAGE_LIMIT_EXCEEDED', 'Documents must contain between 1 and 3 pages.')
                for page in doc:
                    if page.rect.is_empty or page.rect.is_infinite:
                        fail('CORRUPTED_FILE', 'The PDF contains an invalid page.')
                    pixels = page.rect.width * page.rect.height * (settings.ocr_dpi / 72) ** 2
                    if pixels > settings.max_image_pixels:
                        fail('PAGE_TOO_LARGE', 'A PDF page exceeds the safe rendering limit.', 413)
                    page.get_pixmap(matrix=fitz.Matrix(.15, .15))
                if doc.is_repaired:
                    fail('CORRUPTED_FILE', 'The PDF required structural repair. Export a clean copy.')
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as im:
                    if im.width * im.height > settings.max_image_pixels:
                        fail('IMAGE_TOO_LARGE', 'The image exceeds the safe pixel limit.', 413)
                    if getattr(im, 'n_frames', 1) != 1:
                        fail('MULTIFRAME_IMAGE', 'Upload a single JPG or PNG image.')
                    result.page_count = 1
                    im.verify()
                with Image.open(io.BytesIO(data)) as im:
                    im.load()
    except AppError:
        raise
    except Exception:
        fail('CORRUPTED_FILE', 'The file could not be read. Upload a valid PDF / JPG / PNG.')
    result.is_readable, result.status = True, 'PASS'
    return result
