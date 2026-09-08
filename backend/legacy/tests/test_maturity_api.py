import json

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api import maturity
from app.api.deps import get_current_user
from app.models.user import User, UserRole


def passed_gate_payload(scope: str, required_names: set[str]) -> str:
    return json.dumps(
        {
            "generated_at": "2026-07-18T01:00:00+00:00",
            "scope": scope,
            "passed": True,
            "checks": [{"name": name, "passed": True} for name in sorted(required_names)],
            "failures": [],
        }
    )


def client(tmp_path, monkeypatch, authenticated: bool = True, final_gate_payload: str | None = None) -> TestClient:
    docs = tmp_path / "docs" / "experiments"
    docs.mkdir(parents=True)
    (docs / "main-maturity-gate-latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T00:00:00+00:00",
                "scope": "full-system release-candidate maturity gate",
                "passed": True,
                "groups": {name: [{"name": name, "passed": True}] for name in maturity.REQUIRED_GATE_ITEMS["internal_release"]},
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    final_gate = final_gate_payload or '{"generated_at": "2026-07-18T01:00:00+00:00", "passed": false, "failures": [{"name": "long soak evidence passed"}]}'
    (docs / "final-maturity-gate-latest.json").write_text(final_gate, encoding="utf-8")
    (docs / "confirmatory-review-completion-latest.json").write_text(
        '{"generated_at": "2026-07-18T02:00:00+00:00", "passed": false, "failures": [{"name": "human review export exists"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(maturity, "ROOT", tmp_path)
    monkeypatch.setattr(maturity, "GATES", [
        ("internal_release", "内部门禁", docs / "main-maturity-gate-latest.json", "full-system release-candidate maturity gate"),
        ("final_maturity", "最终成熟门禁", docs / "final-maturity-gate-latest.json", "final maturity gate for confirmatory human review"),
        ("confirmatory_review_completion", "确认性人工评审完成门禁", docs / "confirmatory-review-completion-latest.json", "confirmatory human review completion gate"),
    ])
    app = FastAPI()
    app.include_router(maturity.router)

    def override_user():
        if not authenticated:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return User(id=1, username="admin", display_name="Admin", role=UserRole.SUPER_ADMIN)

    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


def test_maturity_status_exposes_final_gate_blockers(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch).get("/maturity/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is False
    assert payload["human_review_allowed"] is False
    assert payload["human_review_report_allowed"] is False
    assert payload["gates"][0]["passed"] is True
    assert payload["gates"][1]["key"] == "final_maturity"
    assert payload["gates"][1]["generated_at"] == "2026-07-18T01:00:00+00:00"
    assert payload["gates"][1]["blockers"] == ["long soak evidence passed"]


def test_maturity_status_includes_simple_failure_detail(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload='{"passed": false, "failures": [{"name": "long soak evidence passed", "detail": "missing: docs/system-evidence/long-soak-latest.json"}]}',
    ).get("/maturity/status")

    assert response.status_code == 200
    assert response.json()["gates"][1]["blockers"] == [
        "long soak evidence passed: missing: docs/system-evidence/long-soak-latest.json"
    ]


def test_maturity_status_includes_manifest_missing_paths(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=(
            '{"passed": false, "failures": [{"name": "final maturity evidence manifest verified", '
            '"detail": {"missing_required_paths": ["docs/a.json", "docs/b.json"]}}]}'
        ),
    ).get("/maturity/status")

    assert response.status_code == 200
    assert response.json()["gates"][1]["blockers"] == [
        "final maturity evidence manifest verified: missing docs/a.json, docs/b.json"
    ]


def test_maturity_status_summarizes_structured_production_config_detail(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=json.dumps(
            {
                "passed": False,
                "failures": [
                    {
                        "name": "production configuration was checked in production mode",
                        "detail": {
                            "standalone": {
                                "status": "skipped_non_production",
                                "checks": {
                                    "app_env_is_production": False,
                                    "secret_key_non_default": False,
                                    "seed_demo_data_disabled": True,
                                },
                            },
                            "embedded": {"status": "skipped_non_production", "checks": {}},
                        },
                    }
                ],
            }
        ),
    ).get("/maturity/status")

    assert response.status_code == 200
    assert response.json()["gates"][1]["blockers"] == [
        "production configuration was checked in production mode: standalone=skipped_non_production; embedded=skipped_non_production; failed checks: app_env_is_production, secret_key_non_default"
    ]


def test_maturity_status_summarizes_nested_gate_detail(tmp_path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "experiments"
    app_client = client(tmp_path, monkeypatch)
    (docs / "confirmatory-review-completion-latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T02:00:00+00:00",
                "passed": False,
                "failures": [
                    {
                        "name": "final maturity gate passed before reporting review",
                        "detail": {
                            "source": "/tmp/final-maturity-gate-latest.json",
                            "scope": "final maturity gate for confirmatory human review",
                            "passed": False,
                            "failures_empty": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    response = app_client.get("/maturity/status")

    assert response.status_code == 200
    assert response.json()["gates"][2]["blockers"] == [
        "final maturity gate passed before reporting review: passed=False; failures_empty=False; scope=final maturity gate for confirmatory human review; source=/tmp/final-maturity-gate-latest.json"
    ]


def test_maturity_status_requires_login(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, authenticated=False).get("/maturity/status")

    assert response.status_code == 401


def test_maturity_status_treats_corrupt_gate_report_as_failed(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, final_gate_payload="{not-json").get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["generated_at"] is None
    assert final_gate["blockers"] == ["invalid JSON: Expecting property name enclosed in double quotes"]


def test_maturity_status_treats_non_object_gate_report_as_failed(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, final_gate_payload="[]").get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["gate report must be a JSON object"]


def test_maturity_status_reports_failed_gate_without_failure_details(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, final_gate_payload='{"passed": false}').get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["gate report is failed but contains no failure details"]


def test_maturity_status_rejects_non_boolean_passed_field(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, final_gate_payload='{"passed": "false", "failures": []}').get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid passed field: expected boolean true/false, got str"]


def test_maturity_status_rejects_passed_gate_with_failure_entries(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    payload["failures"] = [{"name": "long soak evidence passed"}]
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=json.dumps(payload),
    ).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["long soak evidence passed"]


def test_maturity_status_rejects_passed_gate_without_generated_at(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    del payload["generated_at"]
    response = client(tmp_path, monkeypatch, final_gate_payload=json.dumps(payload)).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid generated_at field: expected timestamp string for passed gate"]


def test_maturity_status_rejects_passed_gate_with_unparseable_generated_at(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    payload["generated_at"] = "not-a-timestamp"
    response = client(tmp_path, monkeypatch, final_gate_payload=json.dumps(payload)).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid generated_at field: expected ISO timestamp string for passed gate"]


def test_maturity_status_rejects_passed_gate_with_future_generated_at(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    payload["generated_at"] = "2999-01-01T00:00:00+00:00"
    response = client(tmp_path, monkeypatch, final_gate_payload=json.dumps(payload)).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid generated_at field: timestamp is in the future"]


def test_maturity_status_rejects_passed_gate_without_explicit_failures_list(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    del payload["failures"]
    response = client(tmp_path, monkeypatch, final_gate_payload=json.dumps(payload)).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid failures field: expected explicit empty list for passed gate"]


def test_maturity_status_reports_invalid_failures_field(tmp_path, monkeypatch) -> None:
    response = client(tmp_path, monkeypatch, final_gate_payload='{"passed": false, "failures": {"name": "bad"}}').get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid failures field: expected list, got dict"]


def test_maturity_status_rejects_passed_gate_with_wrong_scope(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=passed_gate_payload("full-system release-candidate maturity gate", maturity.REQUIRED_GATE_ITEMS["final_maturity"]),
    ).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid scope field: expected final maturity gate for confirmatory human review"]


def test_maturity_status_rejects_passed_gate_without_checks(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload='{"generated_at": "2026-07-18T01:00:00+00:00", "scope": "final maturity gate for confirmatory human review", "passed": true, "failures": []}',
    ).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid checks field: expected non-empty list for passed gate"]


def test_maturity_status_rejects_passed_gate_with_failed_check(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    payload["checks"][0]["passed"] = False
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=json.dumps(payload),
    ).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid checks field: every check must be passed"]


def test_maturity_status_rejects_passed_internal_gate_without_group_checks(tmp_path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "experiments"
    app_client = client(tmp_path, monkeypatch)
    (docs / "main-maturity-gate-latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T00:00:00+00:00",
                "scope": "full-system release-candidate maturity gate",
                "passed": True,
                "groups": {name: [] for name in maturity.REQUIRED_GATE_ITEMS["internal_release"]},
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    response = app_client.get("/maturity/status")

    assert response.status_code == 200
    internal_gate = response.json()["gates"][0]
    assert internal_gate["passed"] is False
    assert internal_gate["blockers"] == [
        "invalid groups field: empty required groups agent, evidence_manifest, rag_experiment, retrieval, system"
    ]


def test_maturity_status_rejects_passed_internal_gate_missing_required_group(tmp_path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "experiments"
    app_client = client(tmp_path, monkeypatch)
    (docs / "main-maturity-gate-latest.json").write_text(
        '{"generated_at": "2026-07-18T00:00:00+00:00", "scope": "full-system release-candidate maturity gate", "passed": true, "groups": {"system": [{"name": "internal", "passed": true}]}, "failures": []}',
        encoding="utf-8",
    )

    response = app_client.get("/maturity/status")

    assert response.status_code == 200
    internal_gate = response.json()["gates"][0]
    assert internal_gate["passed"] is False
    assert internal_gate["blockers"] == [
        "invalid groups field: missing required groups agent, evidence_manifest, rag_experiment, retrieval"
    ]


def test_maturity_status_rejects_passed_internal_gate_with_one_empty_required_group(tmp_path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "experiments"
    app_client = client(tmp_path, monkeypatch)
    groups = {name: [{"name": name, "passed": True}] for name in maturity.REQUIRED_GATE_ITEMS["internal_release"]}
    groups["retrieval"] = []
    (docs / "main-maturity-gate-latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T00:00:00+00:00",
                "scope": "full-system release-candidate maturity gate",
                "passed": True,
                "groups": groups,
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    response = app_client.get("/maturity/status")

    assert response.status_code == 200
    internal_gate = response.json()["gates"][0]
    assert internal_gate["passed"] is False
    assert internal_gate["blockers"] == ["invalid groups field: empty required groups retrieval"]


def test_maturity_status_rejects_passed_final_gate_missing_required_check(tmp_path, monkeypatch) -> None:
    payload = json.loads(passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]))
    payload["checks"] = [item for item in payload["checks"] if item["name"] != "long soak evidence passed"]
    response = client(tmp_path, monkeypatch, final_gate_payload=json.dumps(payload)).get("/maturity/status")

    assert response.status_code == 200
    final_gate = response.json()["gates"][1]
    assert final_gate["passed"] is False
    assert final_gate["blockers"] == ["invalid checks field: missing required checks long soak evidence passed"]


def test_maturity_status_separates_review_start_from_result_reporting(tmp_path, monkeypatch) -> None:
    response = client(
        tmp_path,
        monkeypatch,
        final_gate_payload=passed_gate_payload("final maturity gate for confirmatory human review", maturity.REQUIRED_GATE_ITEMS["final_maturity"]),
    ).get("/maturity/status")

    payload = response.json()
    assert payload["human_review_allowed"] is True
    assert payload["human_review_report_allowed"] is False
