from __future__ import annotations

import gzip
import subprocess
from types import SimpleNamespace

import pytest

import app.services.ocr as ocr_module
from app.models.file import StoredFile
from app.models.ocr import FileOcrResult, OcrReviewStatus
from app.services.ocr import OcrService, UnsupportedFileTypeError


class FakeQuery:
    def __init__(self, result) -> None:
        self.result = result

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def first(self):
        return self.result


class FakeDb:
    def __init__(self, record: StoredFile, ocr_result: FileOcrResult | None = None) -> None:
        self.record = record
        self.ocr_result = ocr_result

    def get(self, model, file_id: int):
        assert model is StoredFile
        return self.record if file_id == self.record.id else None

    def query(self, model):
        assert model is FileOcrResult
        return FakeQuery(self.ocr_result)


def stored_file(path, file_id: int = 1, original_filename: str | None = None) -> StoredFile:
    return StoredFile(
        id=file_id,
        project_id=1,
        uploaded_by=1,
        original_filename=original_filename or path.name,
        storage_path=str(path),
        file_size=path.stat().st_size,
        file_hash="test",
    )


def test_extracts_gzipped_geo_soft_text(tmp_path) -> None:
    path = tmp_path / "stored-object.gz"
    with gzip.open(path, "wt", encoding="utf-8") as target:
        target.write("^SERIES = GSE111619\n!Series_sample_id = GSM3035185\n")

    record = stored_file(path, original_filename="GSE111619_family.soft.gz")
    result = OcrService().extract(FakeDb(record), 1)

    assert "GSE111619" in result["extracted_text"]
    assert result["extraction_method"] == "gzip_text"
    assert result["truncated"] is False


def test_reports_truncation_instead_of_silently_slicing(tmp_path, monkeypatch) -> None:
    path = tmp_path / "counts.tsv"
    path.write_text("0123456789" * 10, encoding="utf-8")
    monkeypatch.setattr(
        ocr_module,
        "get_settings",
        lambda: SimpleNamespace(document_text_max_chars=50),
    )

    result = OcrService().extract(FakeDb(stored_file(path)), 1)

    assert result["truncated"] is True
    assert result["character_count"] == 50
    assert result["extracted_text"].endswith("characters]")


def test_extracts_image_with_tesseract(tmp_path, monkeypatch) -> None:
    path = tmp_path / "gel.png"
    path.write_bytes(b"not-a-real-image")
    record = stored_file(path)

    monkeypatch.setattr(ocr_module.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(OcrService, "_tesseract_languages", staticmethod(lambda _executable: {"chi_sim", "eng"}))

    def fake_preprocess(source, output, mode):
        assert source == path
        assert mode == "grayscale_otsu"
        output.write_bytes(b"processed")

    monkeypatch.setattr(ocr_module, "preprocess_image", fake_preprocess)

    def fake_run(command, **_kwargs):
        assert command[0] == "/usr/bin/tesseract"
        assert command[1].endswith("/input.png")
        assert command[2:] == ["stdout", "-l", "chi_sim+eng", "--psm", "3"]
        return subprocess.CompletedProcess(command, 0, stdout="实验编号 EXP-001\n温度 58 C\n", stderr="")

    monkeypatch.setattr(ocr_module.subprocess, "run", fake_run)
    result = OcrService().extract(FakeDb(record), 1)

    assert "EXP-001" in result["extracted_text"]
    assert result["extraction_method"] == "tesseract:chi_sim+eng;preprocess=grayscale_otsu;psm=3"
    assert result["character_count"] > 0


def test_uses_configured_ocr_languages(tmp_path, monkeypatch) -> None:
    path = tmp_path / "notes.jpg"
    path.write_bytes(b"not-a-real-image")
    record = stored_file(path)

    monkeypatch.setattr(ocr_module.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(OcrService, "_tesseract_languages", staticmethod(lambda _executable: {"ukr", "eng"}))
    monkeypatch.setattr(
        ocr_module,
        "get_settings",
        lambda: SimpleNamespace(
            document_text_max_chars=1000,
            ocr_languages="ukr+eng",
            ocr_preprocessing="none",
            ocr_page_segmentation_mode=6,
        ),
    )

    def fake_run(command, **_kwargs):
        assert command == [
            "/usr/bin/tesseract",
            str(path),
            "stdout",
            "-l",
            "ukr+eng",
            "--psm",
            "6",
        ]
        return subprocess.CompletedProcess(command, 0, stdout="Результат 42\n", stderr="")

    monkeypatch.setattr(ocr_module.subprocess, "run", fake_run)
    result = OcrService().extract(FakeDb(record), 1)

    assert result["extraction_method"] == "tesseract:ukr+eng;preprocess=none;psm=6"


def test_rejects_missing_configured_ocr_language(tmp_path, monkeypatch) -> None:
    path = tmp_path / "notes.jpg"
    path.write_bytes(b"not-a-real-image")
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(OcrService, "_tesseract_languages", staticmethod(lambda _executable: {"eng"}))
    monkeypatch.setattr(
        ocr_module,
        "get_settings",
        lambda: SimpleNamespace(document_text_max_chars=1000, ocr_languages="ukr"),
    )

    with pytest.raises(UnsupportedFileTypeError, match="language data is missing: ukr"):
        OcrService().extract(FakeDb(stored_file(path)), 1)


def test_rejects_image_when_ocr_engine_is_missing(tmp_path, monkeypatch) -> None:
    path = tmp_path / "gel.png"
    path.write_bytes(b"not-a-real-image")
    monkeypatch.setattr(ocr_module.shutil, "which", lambda _name: None)

    with pytest.raises(UnsupportedFileTypeError, match="engine is not installed"):
        OcrService().extract(FakeDb(stored_file(path)), 1)


def test_image_must_have_confirmed_ocr_before_indexing(tmp_path) -> None:
    path = tmp_path / "gel.png"
    path.write_bytes(b"image")
    record = stored_file(path)

    with pytest.raises(ValueError, match="reviewed and confirmed"):
        OcrService().extract_for_indexing(FakeDb(record), record)


def test_indexing_uses_human_corrected_ocr_text(tmp_path) -> None:
    path = tmp_path / "gel.png"
    path.write_bytes(b"image")
    record = stored_file(path)
    result = FileOcrResult(
        id=7,
        file_id=record.id,
        project_id=record.project_id,
        created_by=1,
        file_hash=record.file_hash,
        raw_text="实验温度58C",
        corrected_text="实验温度 58 °C",
        extraction_method="tesseract:chi_sim+eng",
        character_count=11,
        review_status=OcrReviewStatus.CONFIRMED.value,
    )

    assert OcrService().extract_for_indexing(FakeDb(record, result), record) == "实验温度 58 °C"
