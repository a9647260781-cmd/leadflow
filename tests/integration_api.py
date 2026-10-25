"""Live API smoke test for the locally running LeadFlow stack.

Reads ignored env files, never prints credentials, and uses only the standard
library so it can run with the system Python.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1:8080"
API = f"{ORIGIN}/api"


def load_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        os.environ[name] = value


def call(opener, method: str, path: str, payload=None, *, origin: bool = False):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if origin:
        headers["Origin"] = ORIGIN
    request = Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=5) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read()
        parsed = json.loads(body) if body else None
        return exc.code, parsed


def main() -> int:
    load_env(ROOT / ".runtime" / "demo-credentials.env")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    assert call(opener, "GET", "/auth/me")[0] == 401

    submission_id = str(uuid.uuid4())
    lead_payload = {
        "submission_id": submission_id,
        "name": "Интеграционный тест",
        "phone": "+7 999 000-00-01",
        "description": "Проверка API, авторизации, идемпотентности и истории статусов.",
    }
    assert call(opener, "POST", "/leads", lead_payload)[0] == 403
    created_status, created = call(opener, "POST", "/leads", lead_payload, origin=True)
    assert created_status == 201
    replay_status, replay = call(opener, "POST", "/leads", lead_payload, origin=True)
    assert replay_status == 200 and replay["id"] == created["id"]

    login_payload = {
        "email": os.environ["MANAGER_EMAIL"],
        "password": os.environ["MANAGER_PASSWORD"],
    }
    assert call(opener, "POST", "/auth/login", login_payload)[0] == 403
    assert call(opener, "POST", "/auth/login", login_payload, origin=True)[0] == 200

    listing_status, listing = call(opener, "GET", "/leads?page=1&page_size=20")
    assert listing_status == 200
    assert any(item["id"] == created["id"] for item in listing["items"])

    detail_status, detail = call(opener, "GET", f"/leads/{created['id']}")
    assert detail_status == 200 and detail["status"] == "new"
    patch_status, updated = call(
        opener,
        "PATCH",
        f"/leads/{created['id']}",
        {"status": "in_progress"},
        origin=True,
    )
    assert patch_status == 200 and updated["status"] == "in_progress"
    assert len(updated["history"]) >= 2

    assert call(opener, "POST", "/auth/logout", {}, origin=True)[0] == 204
    assert call(opener, "GET", f"/leads/{created['id']}")[0] == 401

    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "latest-api-lead-id.txt").write_text(created["id"], encoding="utf-8")
    print("PASS: unauthorized, Origin, idempotency, login, list, detail, status history, logout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
