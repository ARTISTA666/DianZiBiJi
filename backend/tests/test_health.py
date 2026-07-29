from sqlalchemy.exc import OperationalError
from fastapi.testclient import TestClient

from app import main


class FakeSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    def execute(self, _statement) -> None:
        if self.error:
            raise self.error

    def close(self) -> None:
        self.closed = True


def test_readiness_checks_database_and_storage_and_closes_session(monkeypatch, tmp_path) -> None:
    session = FakeSession()
    monkeypatch.setattr(main, "SessionLocal", lambda: session)
    monkeypatch.setattr(main, "STORAGE_ROOT", tmp_path)

    result = main.ready()

    assert result["database"] == result["storage"] == "ok"
    assert session.closed is True


def test_readiness_returns_503_when_database_is_unavailable(monkeypatch, tmp_path) -> None:
    session = FakeSession(OperationalError("SELECT 1", {}, RuntimeError("offline")))
    monkeypatch.setattr(main, "SessionLocal", lambda: session)
    monkeypatch.setattr(main, "STORAGE_ROOT", tmp_path)

    try:
        main.ready()
    except main.HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "Database unavailable"
    else:
        raise AssertionError("readiness should fail")
    assert session.closed is True


def test_readiness_returns_503_when_storage_is_unavailable(monkeypatch, tmp_path) -> None:
    session = FakeSession()
    monkeypatch.setattr(main, "SessionLocal", lambda: session)
    monkeypatch.setattr(main, "STORAGE_ROOT", tmp_path / "missing")

    try:
        main.ready()
    except main.HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "Storage unavailable"
    else:
        raise AssertionError("readiness should fail")
    assert session.closed is True


def test_request_id_is_validated_and_returned() -> None:
    client = TestClient(main.app)

    accepted = client.get("/health", headers={"X-Request-ID": "probe-123"})
    replaced = client.get("/health", headers={"X-Request-ID": "invalid request id"})

    assert accepted.headers["X-Request-ID"] == "probe-123"
    assert replaced.headers["X-Request-ID"] != "invalid request id"
    assert len(replaced.headers["X-Request-ID"]) == 32


def test_runtime_metrics_track_requests() -> None:
    main._reset_metrics_for_tests()
    client = TestClient(main.app)

    client.get("/health")
    client.get("/missing")
    response = client.get("/metrics")

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["total_requests"] >= 2
    assert payload["status_counts"]["2xx"] >= 1
    assert payload["status_counts"]["4xx"] >= 1
    assert payload["latency_sample_count"] >= 2
    assert payload["p95_duration_ms"] >= 0


def test_runtime_metrics_expose_prometheus_text_when_requested() -> None:
    main._reset_metrics_for_tests()
    client = TestClient(main.app)

    client.get("/health")
    response = client.get("/metrics", headers={"Accept": "text/plain"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE eln_requests_total counter" in body
    assert "eln_requests_total 1" in body
    assert 'eln_requests_by_status_total{family="2xx"} 1' in body
    assert 'eln_llm_tokens_total{kind="total"}' in body

    json_response = client.get("/metrics", headers={"Accept": "application/json"})
    assert json_response.headers["content-type"].startswith("application/json")
    assert json_response.json()["status"] == "ok"
