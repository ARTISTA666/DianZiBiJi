from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_agent_probe.py"
SPEC = importlib.util.spec_from_file_location("validate_agent_probe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_summarize_agent_runs_counts_review_states() -> None:
    runs = [
        {"status": "completed", "input_params_json": {"review_result": {"invalid_citations": []}}},
        {"status": "needs_review", "input_params_json": {"review_result": {"invalid_citations": ["[N999]"]}}},
        {"status": "failed", "input_params_json": {}},
    ]

    summary = MODULE.summarize_runs(runs)

    assert summary == {
        "completed_runs": 1,
        "needs_review_runs": 1,
        "failed_runs": 1,
        "invalid_citations": 1,
        "invalid_citation_values": ["[N999]"],
    }


def test_run_probe_calls_all_requested_task_types() -> None:
    class FakeApi:
        posted: list[str] = []

        @staticmethod
        def get(path: str):
            assert path == "/projects"
            return [{"id": 7, "name": "Project"}]

        def post(self, path: str, **kwargs):
            assert path == "/api/agents/generate"
            task_type = kwargs["json"]["task_type"]
            self.posted.append(task_type)
            return {
                "id": len(self.posted),
                "task_type": task_type,
                "status": "completed",
                "input_params_json": {"review_result": {"invalid_citations": []}},
            }

    api = FakeApi()
    report = MODULE.run_probe(api, "Project", ("experiment_summary", "graph_overview"))

    assert api.posted == ["experiment_summary", "graph_overview"]
    assert report["completed_runs"] == 2
    assert report["invalid_citations"] == 0
