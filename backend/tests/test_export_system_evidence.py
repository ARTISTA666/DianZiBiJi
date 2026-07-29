from app.main import app
from scripts.export_system_evidence import collect_openapi_rows, mermaid_label


def test_openapi_export_contains_unique_real_operations() -> None:
    rows = collect_openapi_rows(app.openapi())
    identities = {(row["method"], row["path"]) for row in rows}

    assert len(rows) == len(identities)
    assert ("POST", "/auth/login") in identities
    assert ("POST", "/api/ocr/extract") in identities
    assert ("GET", "/maturity/status") in identities
    assert ("POST", "/projects/{project_id}/rag/query") in identities


def test_mermaid_label_removes_breaking_characters() -> None:
    assert mermaid_label('line "one"\nline two') == "line 'one' line two"
