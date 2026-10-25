"""Loopback-only Telegram sendMessage fixture for notification integration tests."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


COUNTS: dict[str, int] = defaultdict(int)
TOTAL = 0
NEXT_MESSAGE_ID = 1000


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFlowTelegramFixture/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/state":
            self.send_error(404)
            return
        self._json(200, {"total": TOTAL, "rate_limit": COUNTS["rate"], "timeout": COUNTS["timeout"]})

    def do_POST(self) -> None:  # noqa: N802
        global NEXT_MESSAGE_ID, TOTAL
        if not self.path.startswith("/bot") or not self.path.endswith("/sendMessage"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            text = payload["text"]
            chat_id = payload["chat_id"]
            if not isinstance(text, str) or chat_id != "fixture-chat":
                raise ValueError
        except (KeyError, TypeError, ValueError):
            self.send_error(400)
            return

        TOTAL += 1
        if "[rate-limit-once]" in text:
            COUNTS["rate"] += 1
            if COUNTS["rate"] == 1:
                self._json(
                    429,
                    {
                        "ok": False,
                        "error_code": 429,
                        "parameters": {"retry_after": 1},
                    },
                )
                return
        if "[timeout]" in text:
            COUNTS["timeout"] += 1
            time.sleep(2.0)

        NEXT_MESSAGE_ID += 1
        try:
            self._json(200, {"ok": True, "result": {"message_id": NEXT_MESSAGE_ID}})
        except (BrokenPipeError, ConnectionResetError):
            return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18081), Handler).serve_forever()
