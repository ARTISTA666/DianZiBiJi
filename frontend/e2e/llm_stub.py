from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._send(200, {"status": "ok"})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        payload = {}
        if length:
            payload = json.loads(self.rfile.read(length))
        if "E2E_DELAY" in json.dumps(payload, ensure_ascii=False):
            time.sleep(3)
        self._send(
            200,
            {
                "id": "e2e-request",
                "model": "e2e-stub",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "E2E 固定回答：PCR 记录使用 Taq DNA Polymerase，并保留了来源证据。",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
            },
        )

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
