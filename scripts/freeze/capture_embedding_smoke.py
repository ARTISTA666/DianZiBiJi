#!/usr/bin/env python3
"""Capture a version-bound bge-m3 embedding smoke evidence file.

Runs from inside the backend container (or any host that can reach the
configured EMBEDDING_API_URL) and records:

  - the backend revision reported by /ready (proves version binding)
  - the embedding backend / model / dimension from configuration
  - a live 1024-dim bge-m3 probe through the configured embedding API
  - a vector fingerprint (first 16 components) so the run is auditable
    without persisting the full vector

Output: docs/system-evidence/embedding-bge-m3-1024-<timestamp>.json

This produces *run* evidence (bge-m3 1024-dim was actually served against a
revision-bound backend), replacing the prior BLOCKED state that only had the
hash test-double. It does NOT index or modify any knowledge base content.

Usage (default: probe the in-container backend + API URL):
    python scripts/freeze/capture_embedding_smoke.py

    BACKEND_READY_URL=http://127.0.0.1:8000/ready \
    EMBEDDING_API_URL=http://host.docker.internal:11434/v1/embeddings \
    EMBEDDING_MODEL=BAAI/bge-m3 \
    EMBEDDING_DIMENSION=1024 \
    python scripts/freeze/capture_embedding_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "system-evidence"
PROBE_TEXT = "科研电子实验笔记系统 bge-m3 1024 维嵌入运行冒烟"
FINGERPRINT_N = 16


def http_json(url: str, payload: dict | None = None, timeout: int = 8) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ready_url = os.environ.get(
        "BACKEND_READY_URL", "http://127.0.0.1:8000/ready"
    )
    embed_url = os.environ["EMBEDDING_API_URL"]
    model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
    expected_dim = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))
    backends_raw = os.environ.get("EMBEDDING_BACKEND", "openai_compatible")

    record: dict = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "probe_text": PROBE_TEXT,
        "config": {
            "embedding_backend": backends_raw,
            "embedding_model": model,
            "embedding_dimension": expected_dim,
            "embedding_api_url": embed_url,
        },
    }

    # 1. Version binding: backend revision reported by /ready.
    try:
        ready = http_json(ready_url, timeout=5)
        record["backend_ready"] = ready
        record["revision"] = ready.get("revision")
    except Exception as error:  # noqa: BLE001
        record["backend_ready_error"] = repr(error)
        # A missing live endpoint is a failed probe, never an invitation to
        # trust a caller-supplied legacy revision value.
        record["revision"] = None

    # 2. Live bge-m3 probe through the configured embedding API.
    start = time.monotonic()
    try:
        body = http_json(embed_url, {"model": model, "input": [PROBE_TEXT]}, timeout=30)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        data = body.get("data") or []
        if not data or "embedding" not in data[0]:
            raise RuntimeError("embedding response missing data[].embedding")
        vector = data[0]["embedding"]
        record["embedding_probe"] = {
            "served_model": body.get("model"),
            "dimension": len(vector),
            "dimension_matches_config": len(vector) == expected_dim,
            "elapsed_ms": elapsed_ms,
            "fingerprint": [round(v, 9) for v in vector[:FINGERPRINT_N]],
        }
        record["passed"] = (
            len(vector) == expected_dim
            and bool(record.get("revision"))
            and record.get("revision") != "unversioned"
        )
    except Exception as error:  # noqa: BLE001
        record["embedding_probe_error"] = repr(error)
        record["passed"] = False

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"embedding-bge-m3-1024-{ts}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = OUT_DIR / "embedding-bge-m3-1024-latest.json"
    latest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"\nwritten: {out}", file=sys.stderr)
    return 0 if record.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
