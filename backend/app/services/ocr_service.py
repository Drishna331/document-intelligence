"""Page-aware native extraction and bounded local Tesseract fallback."""
import csv
import io
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from PIL import Image, ImageOps
from ..core.errors import AppError
from ..schemas.extraction import SourcePage


def usable(text):
    return sum(c.isalnum() for c in text) >= 35 and '\ufffd' not in text[:1000]


def native_layout(page):
    words = page.get_text('words', sort=True)
    lines = []
    for word in sorted(words, key=lambda w: (round(w[1] / 3), w[0])):
        if not lines or abs(lines[-1][0] - word[1]) > 4:
            lines.append([word[1], []])
        lines[-1][1].append(word)
    return '\n'.join('  '.join(str(w[4]) for w in sorted(row, key=lambda w: w[0])) for _, row in lines)


class OCRService:
    def __init__(self, settings):
        self.settings = settings

    def _run(self, args, timeout):
        try:
            return subprocess.run(args, capture_output=True, timeout=timeout, check=False,
                                  env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
        except subprocess.TimeoutExpired:
            raise AppError('OCR_TIMEOUT', 'Text recognition timed out. Try a clearer scan.', 504) from None
        except OSError:
            raise AppError('OCR_UNAVAILABLE', 'The OCR engine is unavailable.', 503) from None

    def _image(self, im, number):
        if not shutil.which('tesseract'):
            raise AppError('OCR_UNAVAILABLE', 'Tesseract is required for scanned documents.', 503)
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((3500, 5000))
        if im.width < 1400:
            scale = min(2.5, 1400 / im.width)
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS)
        rotation = 0
        with TemporaryDirectory(prefix='docintel-') as directory:
            path = Path(directory) / 'page.png'
            ImageOps.autocontrast(ImageOps.grayscale(im)).save(path)
            def recognize(psm=6):
                result = self._run(['tesseract', str(path), 'stdout', '-l', self.settings.ocr_language,
                                    '--psm', str(psm), '-c', 'preserve_interword_spaces=1', 'tsv'],
                                   self.settings.ocr_timeout_seconds)
                if result.returncode:
                    raise AppError('OCR_FAILED', 'Text recognition failed. Check image clarity and OCR language.', 503)
                rows = csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='replace')), delimiter='\t', quoting=csv.QUOTE_NONE)
                lines, confidences = {}, []
                for row in rows:
                    if row.get('level') != '5' or not (row.get('text') or '').strip():
                        continue
                    key = (row['block_num'], row['par_num'], row['line_num'])
                    lines.setdefault(key, []).append(row)
                    confidence = float(row['conf'])
                    if confidence >= 0:
                        confidences.append(confidence)
                text_lines = []
                for words in lines.values():
                    line, previous = '', None
                    for word in words:
                        gap = int(word['left']) - previous if previous is not None else 0
                        line += ('  ' if gap > 25 else ' ' if previous is not None else '') + word['text']
                        previous = int(word['left']) + int(word['width'])
                    text_lines.append(line)
                return '\n'.join(text_lines), (sum(confidences) / len(confidences) if confidences else 0)

            text, confidence = recognize()
            # Sparse receipts can make OSD incorrectly recommend 180 degrees.
            # Only investigate orientation for weak OCR, and keep a rotation
            # only when actual recognized-word quality improves substantially.
            if confidence < 80:
                try:
                    orientation = self._run(['tesseract', str(path), 'stdout', '--psm', '0'],
                                            min(12, self.settings.ocr_timeout_seconds))
                except AppError:
                    orientation = None
                if orientation is not None and orientation.returncode == 0:
                    match = re.search(r'Rotate:\s*(\d+)', orientation.stdout.decode(errors='replace'))
                    angle = int(match.group(1)) if match else 0
                    if angle:
                        ImageOps.autocontrast(ImageOps.grayscale(im.rotate(-angle, expand=True))).save(path)
                        candidate, candidate_confidence = recognize()
                        if candidate_confidence > confidence + 5 and len(candidate) >= min(100, len(text) * .5):
                            text, confidence, rotation = candidate, candidate_confidence, angle
                        else:
                            ImageOps.autocontrast(ImageOps.grayscale(im)).save(path)
            if confidence < 70:
                candidate, candidate_confidence = recognize(psm=3)
                if candidate_confidence > confidence + 5 and len(candidate) >= len(text) * .8:
                    text, confidence = candidate, candidate_confidence
            return SourcePage(page_number=number, text=text, method='tesseract', rotation_applied=rotation,
                              ocr_mean_word_confidence=round(confidence, 2))

    def extract(self, data, mime):
        pages = []
        try:
            if mime == 'application/pdf':
                with fitz.open(stream=data, filetype='pdf') as doc:
                    for index, page in enumerate(doc):
                        text = native_layout(page)
                        if usable(text):
                            pages.append(SourcePage(page_number=index + 1, text=text, method='native'))
                        else:
                            pix = page.get_pixmap(dpi=self.settings.ocr_dpi, alpha=False)
                            im = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
                            pages.append(self._image(im, index + 1))
            else:
                with Image.open(io.BytesIO(data)) as im:
                    pages.append(self._image(im, 1))
        except AppError:
            raise
        except Exception:
            raise AppError('OCR_FAILED', 'Document text could not be extracted.', 503) from None
        if not any(usable(p.text) for p in pages):
            raise AppError('UNREADABLE_TEXT', 'No usable text was found. Upload a clearer document.', 422)
        if sum(len(p.text) for p in pages) > self.settings.max_text_chars:
            raise AppError('TEXT_TOO_LARGE', 'The extracted text exceeds the processing limit.', 413)
        return pages
