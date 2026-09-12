"""Small explicit environment configuration; secret values never enter responses."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_env(path: Path = ROOT / '.env') -> None:
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


@dataclass(frozen=True)
class Settings:
    host: str = '0.0.0.0'
    port: int = 8000
    database_backend: str = 'sqlite'
    database_path: str = str(ROOT / 'data/documents.sqlite3')
    turso_database_url: str = ''
    turso_auth_token: str = field(default='', repr=False)
    gemini_api_key: str = field(default='', repr=False)
    openai_api_key: str = field(default='', repr=False)
    llm_provider: str = 'gemini'
    llm_model: str = 'gemini-3.8-flash'
    llm_timeout_seconds: float = 120
    ocr_timeout_seconds: float = 40
    ocr_language: str = 'eng'
    ocr_dpi: int = 220
    max_upload_bytes: int = 15 * 1024 * 1024
    max_pages: int = 3
    max_image_pixels: int = 30_000_000
    max_text_chars: int = 100_000
    max_model_response_bytes: int = 4 * 1024 * 1024
    financial_tolerance: str = '0.05'
    max_concurrent_documents: int = 1
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls):
        load_env()
        defaults = cls()
        values = {}
        for key in cls.__dataclass_fields__:
            value = os.getenv(key.upper())
            if value is None:
                continue
            default = getattr(defaults, key)
            if isinstance(default, tuple):
                values[key] = tuple(x.strip() for x in value.split(',') if x.strip())
            elif isinstance(default, int):
                values[key] = int(value)
            elif isinstance(default, float):
                values[key] = float(value)
            else:
                values[key] = value
        result = cls(**values)
        if result.database_backend not in ('sqlite', 'turso'):
            raise ValueError('DATABASE_BACKEND must be sqlite or turso')
        if result.llm_provider not in ('gemini', 'openai'):
            raise ValueError('LLM_PROVIDER must be gemini or openai')
        if result.database_backend == 'turso' and not (result.turso_database_url and result.turso_auth_token):
            raise ValueError('Turso URL and token must be configured')
        if os.getenv('RENDER') and result.database_backend == 'sqlite':
            if not result.database_path.startswith('/var/data/'):
                raise ValueError('Render requires Turso or a mounted /var/data persistent disk')
        if not 1 <= result.max_pages <= 3 or result.max_concurrent_documents < 1:
            raise ValueError('Invalid page or concurrency configuration')
        if not 100 <= result.ocr_dpi <= 300 or result.max_upload_bytes < 1:
            raise ValueError('Invalid OCR resolution or upload limit')
        if result.ocr_timeout_seconds <= 0 or result.llm_timeout_seconds <= 0:
            raise ValueError('Timeouts must be positive')
        from decimal import Decimal
        tolerance = Decimal(result.financial_tolerance)
        if not tolerance.is_finite() or tolerance < 0:
            raise ValueError('FINANCIAL_TOLERANCE must be finite and nonnegative')
        return result
