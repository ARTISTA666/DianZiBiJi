from __future__ import annotations

import gzip
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.file import StoredFile
from app.models.ocr import FileOcrResult, OcrReviewStatus
from app.services.ocr_image import PREPROCESS_MODES, preprocess_image

_ocr_semaphore = threading.Semaphore(3)


class UnsupportedFileTypeError(ValueError):
    pass


class OcrService:
    """Extract searchable text from stored research files."""

    TEXT_EXTENSIONS = {
        ".txt",
        ".csv",
        ".tsv",
        ".soft",
        ".md",
        ".json",
        ".xml",
        ".html",
        ".log",
        ".yaml",
        ".yml",
    }
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}

    def extract_for_indexing(self, db: Session, record: StoredFile) -> str:
        file_path = Path(record.storage_path)
        if file_path.suffix.lower() not in self.IMAGE_EXTENSIONS:
            return self.extract(db, record.id)["extracted_text"]
        latest = (
            db.query(FileOcrResult)
            .filter(FileOcrResult.file_id == record.id)
            .order_by(FileOcrResult.id.desc())
            .first()
        )
        if latest is None or latest.review_status != OcrReviewStatus.CONFIRMED.value:
            raise ValueError("Image OCR must be reviewed and confirmed before indexing")
        if latest.file_hash != record.file_hash:
            raise ValueError("Confirmed OCR does not match the current file")
        return latest.corrected_text

    def extract(self, db: Session, file_id: int) -> dict:
        record = db.get(StoredFile, file_id)
        if record is None:
            raise LookupError(f"File {file_id} not found")

        file_path = Path(record.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Stored file not found at {record.storage_path}")

        max_chars = max(1, get_settings().document_text_max_chars)
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            text = self._extract_pdf(file_path, max_chars)
            method = "pdf_text"
        elif ext == ".gz":
            text = self._extract_gzip_text(file_path, record.original_filename, max_chars)
            method = "gzip_text"
        elif ext in self.IMAGE_EXTENSIONS:
            text, method = self._extract_image(file_path)
        elif ext in self.TEXT_EXTENSIONS:
            text = self._read_text(file_path, max_chars)
            method = "plain_text"
        else:
            raise UnsupportedFileTypeError(f"Unsupported file type: {ext or '[no extension]'}")

        text, truncated = self._limit_text(text, max_chars)

        return {
            "file_id": file_id,
            "extracted_text": text,
            "source_ids": [str(file_id)],
            "character_count": len(text),
            "truncated": truncated,
            "extraction_method": method,
        }

    @staticmethod
    def _extract_image(path: Path) -> tuple[str, str]:
        with _ocr_semaphore:
            executable = shutil.which("tesseract")
            if executable is None:
                raise UnsupportedFileTypeError("Image OCR engine is not installed")
            settings = get_settings()
            try:
                languages = OcrService._tesseract_languages(executable)
            except subprocess.TimeoutExpired as exc:
                raise UnsupportedFileTypeError("Image OCR engine did not respond") from exc
            requested = [
                language.strip()
                for language in settings.ocr_languages.replace(",", "+").split("+")
                if language.strip()
            ]
            if not requested:
                raise UnsupportedFileTypeError("OCR_LANGUAGES is empty")
            missing = [language for language in requested if language not in languages]
            if missing:
                raise UnsupportedFileTypeError(
                    f"Tesseract language data is missing: {', '.join(missing)}"
                )
            language_arg = "+".join(requested)
            preprocessing = getattr(settings, "ocr_preprocessing", "grayscale_otsu").strip()
            if preprocessing not in PREPROCESS_MODES:
                raise UnsupportedFileTypeError(f"Unsupported OCR preprocessing mode: {preprocessing}")
            page_segmentation_mode = getattr(settings, "ocr_page_segmentation_mode", 3)
            if not 0 <= page_segmentation_mode <= 13:
                raise UnsupportedFileTypeError("OCR_PAGE_SEGMENTATION_MODE must be between 0 and 13")

            try:
                with tempfile.TemporaryDirectory(prefix="eln-ocr-") as directory:
                    ocr_path = path
                    if preprocessing != "none":
                        ocr_path = Path(directory) / "input.png"
                        preprocess_image(path, ocr_path, preprocessing)
                    result = subprocess.run(
                        [
                            executable,
                            str(ocr_path),
                            "stdout",
                            "-l",
                            language_arg,
                            "--psm",
                            str(page_segmentation_mode),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
            except subprocess.TimeoutExpired as exc:
                raise UnsupportedFileTypeError("Image OCR timed out after 120 seconds") from exc
            except OSError as exc:
                raise UnsupportedFileTypeError(f"Image preprocessing failed: {exc}") from exc
            if result.returncode != 0:
                message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
                raise UnsupportedFileTypeError(f"Image OCR failed: {message}")
            method = f"tesseract:{language_arg};preprocess={preprocessing};psm={page_segmentation_mode}"
            return result.stdout.strip(), method

    @staticmethod
    def _tesseract_languages(executable: str) -> set[str]:
        result = subprocess.run(
            [executable, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines()[1:] if line.strip()}

    def _extract_gzip_text(self, path: Path, original_filename: str, max_chars: int) -> str:
        inner_extension = Path(Path(original_filename).stem).suffix.lower()
        if inner_extension not in self.TEXT_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Unsupported gzip payload: {inner_extension or '[no extension]'}"
            )
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as source:
            return source.read(max_chars + 1)

    @staticmethod
    def _read_text(path: Path, max_chars: int) -> str:
        with path.open("r", encoding="utf-8", errors="replace") as source:
            return source.read(max_chars + 1)

    @staticmethod
    def _extract_pdf(path: Path, max_chars: int) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts: list[str] = []
            character_count = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                parts.append(page_text)
                character_count += len(page_text) + 1
                if character_count > max_chars:
                    break
            return "\n".join(parts)
        except ImportError:
            pass
        raw = path.read_bytes()
        return "".join(chr(b) for b in raw[:5000] if 32 <= b < 127) + "\n[PDF text extraction requires pypdf]"

    @staticmethod
    def _limit_text(text: str, max_chars: int) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        marker = f"\n[Content truncated at {max_chars} characters]"
        return text[: max(0, max_chars - len(marker))] + marker[:max_chars], True
