from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "evaluate_rust_retrieval.py"
SPEC = importlib.util.spec_from_file_location("evaluate_rust_retrieval", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_response_evidence_preserves_document_then_graph_order() -> None:
    ranking, evidence = MODULE.response_evidence(
        {
            "sources": [{"chunk_id": 11, "filename": "protocol.txt", "snippet": "Taq"}],
            "graph_context": [
                {
                    "relation_id": 9,
                    "source_label": "Taq",
                    "relation_label": "用于",
                    "target_label": "PCR",
                }
            ],
        },
        "graph_enhanced_rag",
    )

    assert ranking == ["graph_enhanced_rag:source:11", "graph_enhanced_rag:graph:9"]
    assert evidence[ranking[0]].text == "Taq"
    assert evidence[ranking[1]].evidence_type == "graph_relation"


def test_response_evidence_ignores_malformed_items() -> None:
    ranking, evidence = MODULE.response_evidence({"sources": [None], "graph_context": [None]}, "bm25")

    assert ranking == []
    assert evidence == {}
