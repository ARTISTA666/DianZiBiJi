"""Scoring checks: wrong triples must never inflate precision/recall."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("t136", Path(__file__).with_name("run_t136_kg_validation.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(**changes):
    item = {"record_id": "a", "source_type": "note", "source_label": "Note A", "source_identity": "a",
            "relation_type": "uses_sample", "target_type": "sample", "target_label": "sample 2", "target_identity": ""}
    return item | changes


def test_complete_triple_rejects_wrong_subject_type_number_and_identity():
    gold = [row()]
    for change in [{"source_label": "Note B"}, {"source_type": "project"}, {"target_type": "reagent"},
                   {"target_label": "sample 20"}, {"source_identity": "another-note"}, {"relation_type": "uses_reagent"}]:
        result = MODULE.score(gold, [row(**change)])
        assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)


def test_duplicates_and_zero_predictions_are_explicit():
    result = MODULE.score([row()], [row(), row()])
    assert result["tp"] == 1 and result["duplicate_rows"] == 1
    result = MODULE.score([row()], [])
    assert result["precision"] is None and result["recall"] == result["f1"] == 0
    result = MODULE.score([], [])
    assert result["f1"] is None and result["exact"]


def test_normalization_keeps_negation_numbers_units_and_punctuation():
    assert MODULE.key(row(target_label="  SAMPLE  ２ ")) == MODULE.key(row())
    assert MODULE.key(row(target_label="not sample 2")) != MODULE.key(row())
    assert MODULE.normalize("10 mM") != MODULE.normalize("10 M")
    assert MODULE.normalize("Failed.") != MODULE.normalize("Failed")


def test_frozen_inputs_and_manifest_fail_on_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    source = tmp_path / "input.json"
    source.write_text("[]")
    manifest = tmp_path / "freeze-manifest.json"
    files = [{"path": "input.json", "sha256": MODULE.sha(source)}]
    for name in ["scripts/experiments/run_t136_kg_validation.py", "docs/experiments/kg-heldout-T136-protocol-v1.md", "inputs/cases.json", "inputs/operator.json"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        files.append({"path": name, "sha256": MODULE.sha(path)})
    manifest.write_text(json.dumps({"files": files}))
    checksum = tmp_path / "freeze.sha256"
    checksum.write_text(MODULE.sha(manifest))
    MODULE.verify_freeze(tmp_path)
    source.write_text("[1]")
    with pytest.raises(ValueError, match="input drift"):
        MODULE.verify_freeze(tmp_path)
    manifest.write_text("{}")
    with pytest.raises(ValueError, match="manifest drift"):
        MODULE.verify_freeze(tmp_path)


def test_decode_preserves_real_subject_and_rejects_wrong_provenance():
    graph = {"project_id": 7, "entities": [
        {"id": 1, "entity_type": "project", "project_id": 7, "source_type": "project", "source_id": 7, "label": "P"},
        {"id": 2, "entity_type": "note", "project_id": 7, "source_type": "note", "source_id": 8, "label": "Note A"}],
        "relations": [{"id": 9, "project_id": 7, "source_id": 8, "source_type": "note", "source_entity_id": 1,
                       "target_entity_id": 2, "relation_type": "has_note", "confidence": 1, "properties": {}}]}
    item = {"project_name": "P", "record_id": "a"}
    rows, excluded = MODULE.decode_graph(graph, item, 7, 8, 1)
    assert not excluded and rows[0]["source_type"] == "project" and rows[0]["target_identity"] == "a"
    graph["relations"][0]["source_id"] = 99
    with pytest.raises(ValueError, match="provenance"):
        MODULE.decode_graph(graph, item, 7, 8, 1)


def test_preflight_rejects_duplicate_cases_and_unpaired_arms():
    with pytest.raises(ValueError, match="duplicate input"):
        MODULE.validate_cases([{"arm": "body", "record_id": "a"}] * 2)
    with pytest.raises(ValueError, match="unpaired"):
        MODULE.validate_cases([{"arm": "body", "record_id": "a"}])
