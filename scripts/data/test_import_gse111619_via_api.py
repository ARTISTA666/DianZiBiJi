from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_gse111619_via_api.py"
SPEC = importlib.util.spec_from_file_location("gse111619_api_import", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_import_plan_uses_verified_notes_and_separates_raw_from_knowledge_files() -> None:
    plan = MODULE.load_import_plan(ROOT / "data" / "real" / "GSE111619")

    assert len(plan["notes"]) == 4
    assert {note["fixed_fields_json"]["source_accession"] for note in plan["notes"]} == MODULE.EXPECTED_ACCESSIONS
    assert all("status" not in note for note in plan["notes"])
    assert [item["category"] for item in plan["files"]].count("note_attachment") == 4
    assert [item["category"] for item in plan["files"]].count("knowledge_document") == 2


def test_existing_file_must_match_both_name_and_hash() -> None:
    item = {"path": Path("source.txt"), "sha256": "expected"}
    matching = {"original_filename": "source.txt", "file_hash": "expected", "id": 7}

    assert MODULE.find_existing_file([matching], item) == matching
    with pytest.raises(ValueError, match="different content"):
        MODULE.find_existing_file(
            [{"original_filename": "source.txt", "file_hash": "different", "id": 8}],
            item,
        )


def test_extraction_summary_keeps_evidence_without_copying_full_text() -> None:
    summary = MODULE.summarize_extraction(
        {"id": 5, "original_filename": "counts.txt.gz"},
        {
            "extracted_text": "GeneID\tcontrol\tknockdown\nENSG1\t1\t2\n",
            "extraction_method": "gzip_text",
            "character_count": 39,
            "truncated": False,
        },
    )

    assert summary["first_line"] == "GeneID\tcontrol\tknockdown"
    assert summary["extraction_method"] == "gzip_text"
    assert summary["extracted_text_sha256"]
    assert "extracted_text" not in summary


def test_benchmark_plan_uses_raw_documents_and_enriched_graph_fields() -> None:
    plan = MODULE.load_import_plan(ROOT / "data" / "real" / "GSE111619", benchmark=True)

    knowledge_names = {
        item["path"].name for item in plan["files"] if item["category"] == "knowledge_document"
    }
    assert knowledge_names == set(MODULE.BENCHMARK_KNOWLEDGE_FILES)
    assert "gse111619_knowledge_document.txt" not in knowledge_names
    first_fields = plan["notes"][0]["fixed_fields_json"]
    assert first_fields["sra_accession"] == "SRX3777456"
    assert first_fields["biosample_accession"] == "SAMN08667775"
    assert first_fields["alignment_method"] == "TopHat2 v2.0.13"
