import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.extraction import ExtractionResult, ProviderError, YandexExtractionClient
from app.schemas import ExtractionWrite


def configured_settings() -> Settings:
    return Settings(
        ai_enabled=True,
        yandex_api_key="test-key",
        yandex_model_uri="gpt://folder/yandexgpt-5.1",
    )


def success_response(result: dict) -> dict:
    return {
        "alternatives": [
            {
                "status": "ALTERNATIVE_STATUS_FINAL",
                "message": {"role": "assistant", "text": json.dumps(result, ensure_ascii=False)},
            }
        ]
    }


def test_twenty_offline_extraction_fixtures_validate_through_real_adapter() -> None:
    path = Path(__file__).parent / "fixtures" / "extraction_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) >= 20

    for case in cases:

        def handler(request: httpx.Request, result: dict = case["result"]) -> httpx.Response:
            return httpx.Response(200, json=success_response(result), request=request)

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as http_client:
            client = YandexExtractionClient(configured_settings(), client=http_client)
            result = client.extract(case["description"])
        assert result.model_dump() == case["result"]


def test_request_uses_structured_output_and_sends_only_description_as_user_data() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        result = {
            "service": None,
            "budget_min": None,
            "budget_max": None,
            "budget_currency": None,
            "budget_text": None,
            "timeframe": None,
            "evidence": {"service": None, "budget": None, "timeframe": None},
        }
        return httpx.Response(200, json=success_response(result), request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = YandexExtractionClient(configured_settings(), client=http_client)
        client.extract("Только описание")

    assert captured["messages"][1] == {"role": "user", "text": "Только описание"}
    assert "2026-10-25" not in captured["messages"][0]["text"]
    assert "jsonSchema" in captured and "tools" not in captured
    assert captured["completionOptions"]["stream"] is False


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (401, "provider_auth", False),
        (403, "provider_auth", False),
        (429, "provider_rate_limited", True),
        (500, "provider_unavailable", True),
        (503, "provider_unavailable", True),
        (400, "provider_request_rejected", False),
    ],
)
def test_provider_http_errors_are_safely_classified(
    status_code: int, code: str, retryable: bool
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, request=request))
    with httpx.Client(transport=transport) as http_client:
        client = YandexExtractionClient(configured_settings(), client=http_client)
        with pytest.raises(ProviderError) as caught:
            client.extract("Описание")
    assert caught.value.code == code
    assert caught.value.retryable is retryable


def test_timeout_is_retryable_and_invalid_evidence_is_rejected() -> None:
    timeout_transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request))
    )
    with httpx.Client(transport=timeout_transport) as http_client:
        with pytest.raises(ProviderError) as timeout:
            YandexExtractionClient(configured_settings(), client=http_client).extract("Описание")
    assert timeout.value.code == "provider_timeout"
    assert timeout.value.retryable

    bad = {
        "service": "ремонт",
        "budget_min": None,
        "budget_max": None,
        "budget_currency": None,
        "budget_text": None,
        "timeframe": None,
        "evidence": {"service": "invented quote", "budget": None, "timeframe": None},
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=success_response(bad), request=request)
    )
    with httpx.Client(transport=transport) as http_client:
        with pytest.raises(ProviderError) as invalid:
            YandexExtractionClient(configured_settings(), client=http_client).extract(
                "Нужен ремонт"
            )
    assert invalid.value.code == "invalid_evidence"


@pytest.mark.parametrize("model", [ExtractionResult, ExtractionWrite])
def test_budget_precision_is_not_silently_rounded(model) -> None:
    payload = {
        "service": None,
        "budget_min": 12.345,
        "budget_max": None,
        "budget_currency": "RUB",
        "budget_text": None,
        "timeframe": None,
        "evidence": {"service": None, "budget": None, "timeframe": None},
    }
    if model is ExtractionWrite:
        payload["expected_revision"] = 0
    with pytest.raises(ValueError):
        model.model_validate(payload)


@pytest.mark.parametrize("wrapped", [False, True])
def test_documented_yandex_response_envelopes_are_supported(wrapped: bool) -> None:
    result = {
        "service": None,
        "budget_min": None,
        "budget_max": None,
        "budget_currency": None,
        "budget_text": None,
        "timeframe": None,
        "evidence": {"service": None, "budget": None, "timeframe": None},
    }
    body = success_response(result)
    if wrapped:
        body = {"result": body}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body, request=request))
    with httpx.Client(transport=transport) as http_client:
        parsed = YandexExtractionClient(configured_settings(), client=http_client).extract(
            "Без деталей"
        )
    assert parsed.service is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"budget_min": None, "budget_max": 999999, "budget_currency": "USD"},
        {"budget_min": None, "budget_max": 5000, "budget_currency": "USD"},
        {"budget_min": 5000, "budget_max": None, "budget_currency": "RUB"},
    ],
)
def test_fabricated_budget_amount_currency_or_direction_is_rejected(overrides: dict) -> None:
    result = {
        "service": "Ремонт",
        "budget_min": None,
        "budget_max": 5000,
        "budget_currency": "RUB",
        "budget_text": "до 5000 рублей",
        "timeframe": None,
        "evidence": {
            "service": "Ремонт",
            "budget": "до 5000 рублей",
            "timeframe": None,
        },
        **overrides,
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=success_response(result), request=request)
    )
    with httpx.Client(transport=transport) as http_client:
        with pytest.raises(ProviderError) as invalid:
            YandexExtractionClient(configured_settings(), client=http_client).extract(
                "Ремонт, бюджет до 5000 рублей."
            )
    assert invalid.value.code == "invalid_budget_grounding"


def test_narrow_nonbreaking_thousands_space_is_grounded_without_crashing() -> None:
    quote = "5\u202f000 рублей"
    result = {
        "service": None,
        "budget_min": 5000,
        "budget_max": 5000,
        "budget_currency": "RUB",
        "budget_text": quote,
        "timeframe": None,
        "evidence": {"service": None, "budget": quote, "timeframe": None},
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=success_response(result), request=request)
    )
    with httpx.Client(transport=transport) as http_client:
        parsed = YandexExtractionClient(configured_settings(), client=http_client).extract(
            f"Бюджет {quote}."
        )
    assert parsed.budget_min == 5000
    assert parsed.budget_max == 5000
