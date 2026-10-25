"""End-to-end AI extraction test against the local provider fixture only."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("LEADFLOW_TEST_API", "http://127.0.0.1:18000/api")
ORIGIN = os.environ.get("LEADFLOW_TEST_ORIGIN", "http://127.0.0.1:18080")


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
        return exc.code, json.loads(body) if body else None


def wait_status(opener, lead_id: str, expected: str, timeout: float = 12.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        status, detail = call(opener, "GET", f"/leads/{lead_id}")
        assert status == 200
        last = detail["extraction"]
        if last["status"] == expected:
            return last
        time.sleep(0.2)
    raise AssertionError(f"extraction did not reach {expected}; last status={last['status']}")


def create_lead(opener, description: str) -> str:
    status, created = call(
        opener,
        "POST",
        "/leads",
        {
            "submission_id": str(uuid.uuid4()),
            "name": "Synthetic Fixture",
            "phone": "+7 999 000-18-081",
            "description": description,
        },
        origin=True,
    )
    assert status == 201
    return created["id"]


def main() -> int:
    load_env(ROOT / ".runtime" / "demo-credentials.env")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    login_status, _ = call(
        opener,
        "POST",
        "/auth/login",
        {"email": os.environ["MANAGER_EMAIL"], "password": os.environ["MANAGER_PASSWORD"]},
        origin=True,
    )
    assert login_status == 200

    description = (
        "Нужен ремонт стиральной машины, бюджет 7000 рублей, срок завтра. [retry-once]"
    )
    lead_id = create_lead(opener, description)
    extracted = wait_status(opener, lead_id, "succeeded")
    assert extracted["attempts"] == 2
    assert extracted["service"] == "ремонт стиральной машины"
    assert extracted["budget_min"] == 7000.0
    assert extracted["budget_max"] == 7000.0
    assert extracted["budget_currency"] == "RUB"
    assert extracted["budget_text"] == "7000 рублей"
    assert extracted["timeframe"] == "завтра"
    assert extracted["evidence"] == {
        "service": "ремонт стиральной машины",
        "budget": "7000 рублей",
        "timeframe": "завтра",
    }

    manual_payload = {
        "expected_revision": extracted["revision"],
        "service": "Диагностика и ремонт",
        "budget_min": 7500,
        "budget_max": 7500,
        "budget_currency": "RUB",
        "budget_text": "7000 рублей",
        "timeframe": "завтра",
        "evidence": {
            "service": "ремонт стиральной машины",
            "budget": "7000 рублей",
            "timeframe": "завтра",
        },
    }
    unauthenticated = build_opener(HTTPCookieProcessor(CookieJar()))
    unauthorized_status, _ = call(
        unauthenticated,
        "PATCH",
        f"/leads/{lead_id}/extraction",
        manual_payload,
        origin=True,
    )
    assert unauthorized_status == 401
    origin_status, _ = call(
        opener, "PATCH", f"/leads/{lead_id}/extraction", manual_payload
    )
    assert origin_status == 403
    patch_status, manual = call(
        opener, "PATCH", f"/leads/{lead_id}/extraction", manual_payload, origin=True
    )
    assert patch_status == 200 and manual["manually_edited"] is True
    protected_status, _ = call(
        opener,
        "POST",
        f"/leads/{lead_id}/extraction/retry",
        {"overwrite_manual": False},
        origin=True,
    )
    assert protected_status == 409
    retry_status, queued = call(
        opener,
        "POST",
        f"/leads/{lead_id}/extraction/retry",
        {"overwrite_manual": True},
        origin=True,
    )
    assert retry_status == 202 and queued["status"] == "pending"
    rerun = wait_status(opener, lead_id, "succeeded")
    assert rerun["manually_edited"] is False and rerun["attempts"] == 1

    failed_id = create_lead(
        opener,
        "Нужен ремонт стиральной машины, бюджет 7000 рублей, срок завтра. [always-fail]",
    )
    failed = wait_status(opener, failed_id, "failed")
    assert failed["error_code"] == "provider_unavailable"
    retry_failed_status, _ = call(
        opener,
        "POST",
        f"/leads/{failed_id}/extraction/retry",
        {"overwrite_manual": False},
        origin=True,
    )
    assert retry_failed_status == 202

    print(
        "PASS fixture-only: pending, transient retry, structured success/evidence, "
        "auth/origin protection, manual protection/edit, explicit rerun, "
        "permanent failure/retry"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
