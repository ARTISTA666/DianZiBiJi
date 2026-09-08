#!/usr/bin/env python3
"""Validate the production reverse-proxy/TLS Nginx template."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "deploy" / "nginx.conf.template"
REQUIRED_SNIPPETS = {
    "http redirects to https": "return 301 https://$host$request_uri;",
    "https listener": "listen 443 ssl",
    "certificate path": "ssl_certificate ${TLS_CERT_PATH};",
    "certificate key path": "ssl_certificate_key ${TLS_KEY_PATH};",
    "modern tls protocols": "ssl_protocols TLSv1.2 TLSv1.3;",
    "hsts header": "Strict-Transport-Security",
    "upload body limit": "client_max_body_size ${CLIENT_MAX_BODY_SIZE};",
    "backend proxy": "proxy_pass http://127.0.0.1:${BACKEND_PORT}/;",
    "frontend proxy": "proxy_pass http://127.0.0.1:${FRONTEND_PORT};",
    "forwarded proto": "proxy_set_header X-Forwarded-Proto https;",
    "request id": "proxy_set_header X-Request-ID $request_id;",
}
PLACEHOLDERS = {"ELN_DOMAIN", "TLS_CERT_PATH", "TLS_KEY_PATH", "CLIENT_MAX_BODY_SIZE", "BACKEND_PORT", "FRONTEND_PORT"}


def check_template(path: Path = DEFAULT_TEMPLATE) -> dict:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    found_placeholders = set(re.findall(r"\$\{([A-Z0-9_]+)\}", text))
    checks = [
        {"name": "template exists", "passed": path.is_file(), "detail": str(path)},
        *[
            {"name": name, "passed": snippet in text, "detail": snippet}
            for name, snippet in REQUIRED_SNIPPETS.items()
        ],
        {
            "name": "all required placeholders present",
            "passed": PLACEHOLDERS <= found_placeholders,
            "detail": {"expected": sorted(PLACEHOLDERS), "actual": sorted(found_placeholders)},
        },
        {
            "name": "no localhost public server_name",
            "passed": "server_name localhost" not in text,
            "detail": "server_name localhost",
        },
    ]
    return {
        "ok": all(item["passed"] for item in checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "template": str(path),
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "system-evidence" / "reverse-proxy-latest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = check_template(args.template)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
