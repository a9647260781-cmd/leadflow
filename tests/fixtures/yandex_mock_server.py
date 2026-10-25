"""Local-only Yandex completion fixture for integration tests.

It never contacts the internet and accepts only loopback traffic. Synthetic
descriptions control deterministic success, retry-once, and permanent failure
responses. Do not use this server as a production provider substitute.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COUNTS: dict[str, int] = defaultdict(int)


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFlowYandexFixture/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/foundationModels/v1/completion":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body)
            messages = payload["messages"]
            description = next(item["text"] for item in messages if item["role"] == "user")
        except (KeyError, StopIteration, TypeError, ValueError):
            self.send_error(400)
            return

        if (
            b"Synthetic Fixture" in raw_body
            or b"+7 999 000-18-081" in raw_body
            or self.headers.get("x-data-logging-enabled") != "false"
        ):
            self.send_error(422)
            return

        COUNTS[description] += 1
        if "[delay-first]" in description and COUNTS[description] == 1:
            delay = float(os.environ.get("LEADFLOW_FIXTURE_DELAY_SECONDS", "0"))
            if delay > 0:
                time.sleep(min(delay, 30.0))
        if "[always-fail]" in description:
            self._json(503, {"error": "synthetic provider failure"})
            return
        if "[retry-once]" in description and COUNTS[description] == 1:
            self._json(503, {"error": "synthetic transient failure"})
            return

        result = {
            "service": "ремонт стиральной машины",
            "budget_min": 7000,
            "budget_max": 7000,
            "budget_currency": "RUB",
            "budget_text": "7000 рублей",
            "timeframe": "завтра",
            "evidence": {
                "service": "ремонт стиральной машины",
                "budget": "7000 рублей",
                "timeframe": "завтра",
            },
        }
        self._json(
            200,
            {
                "result": {
                    "alternatives": [
                        {
                            "status": "ALTERNATIVE_STATUS_FINAL",
                            "message": {"role": "assistant", "text": json.dumps(result)},
                        }
                    ]
                }
            },
        )

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("LEADFLOW_FIXTURE_PORT", "18081"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
