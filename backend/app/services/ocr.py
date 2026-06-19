from pathlib import Path

from sqlalchemy.orm import Session

from app.models.file import StoredFile


class OcrService:
    """从已存储的文件中提取文字（支持 txt / csv / md / pdf 等）"""

    SUPPORTED_EXTENSIONS = {".txt", ".csv", ".md", ".json", ".xml", ".html", ".log"}

    def extract(self, db: Session, file_id: int) -> dict:
        record = db.get(StoredFile, file_id)
        if record is None:
            raise LookupError(f"File {file_id} not found")

        file_path = Path(record.storage_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Stored file not found at {record.storage_path}")

        ext = file_path.suffix.lower()
        if ext == ".pdf":
            text = self._extract_pdf(file_path)
        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"}:
            text = self._extract_image(file_path)
        elif ext in self.SUPPORTED_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        else:
            text = f"[Unsupported file type: {ext}]"

        return {
            "file_id": file_id,
            "extracted_text": text[:50000],
            "source_ids": [str(file_id)],
        }

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        """Extract text from a PDF with the pure-Python pypdf parser."""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            pass
        raw = path.read_bytes()
        return "".join(chr(b) for b in raw[:5000] if 32 <= b < 127) + "\n[PDF text extraction requires pypdf]"

    @staticmethod
    def _extract_image(path: Path) -> str:
        """占位实现——图片 OCR 需要额外服务（Tesseract / OCR API）"""
        return f"[Image file: {path.name}. OCR requires Tesseract or an OCR API.]"
