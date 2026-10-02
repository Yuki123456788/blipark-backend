from collections import Counter

import httpx
import pytest

from integrations.tdx.client import (
    TDXAuthenticationError,
    TDXClient,
    TDXDataset,
    TDXRequestError,
    TDXResponseError,
)


def token_response(token="test-access-token"):
    return {"access_token": token, "expires_in": 3600, "token_type": "Bearer"}


def parking_response(records_key, records, *, count=None):
    return {
        "UpdateTime": "2026-10-03T03:06:32+08:00",
        "UpdateInterval": 14400,
        "SrcUpdateTime": "2026-10-03T03:05:59+08:00",
        "SrcUpdateInterval": -1,
        "AuthorityCode": "TNN",
        "VersionID": 8387,
        "Count": len(records) if count is None else count,
        records_key: records,
    }


def make_client(handler, **overrides):
    options = {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "http_client": httpx.Client(transport=httpx.MockTransport(handler)),
        "page_size": 2,
        "sleeper": lambda _delay: None,
        "jitter": lambda: 0,
    }
    options.update(overrides)
    return TDXClient(
        **options,
    )


def test_client_caches_token_and_paginates_until_count():
    calls = Counter()
    offsets = []

    def handler(request):
        if "openid-connect/token" in str(request.url):
            calls["token"] += 1
            return httpx.Response(200, json=token_response())
        calls["data"] += 1
        assert request.headers["authorization"] == "Bearer test-access-token"
        offset = int(request.url.params["$skip"])
        offsets.append(offset)
        records = [{"ParkingSpotID": str(index)} for index in range(offset, min(offset + 2, 5))]
        return httpx.Response(200, json=parking_response("ParkingSegmentSpots", records, count=5))

    client = make_client(handler)

    pages = list(client.iter_pages(TDXDataset.ON_STREET_SPOTS))

    assert calls == Counter(token=1, data=3)
    assert offsets == [0, 2, 4]
    assert [len(page.records) for page in pages] == [2, 2, 1]


def test_client_honors_retry_after_for_rate_limit():
    delays = []
    data_calls = 0

    def handler(request):
        nonlocal data_calls
        if "openid-connect/token" in str(request.url):
            return httpx.Response(200, json=token_response())
        data_calls += 1
        if data_calls == 1:
            return httpx.Response(429, headers={"Retry-After": "13"}, json={"message": "slow down"})
        return httpx.Response(200, json=parking_response("CarParks", []))

    client = make_client(handler, sleeper=delays.append)

    list(client.iter_pages(TDXDataset.CAR_PARKS))

    assert data_calls == 2
    assert delays == [13]


def test_client_refreshes_token_once_after_unauthorized_response():
    token_calls = 0
    data_calls = 0

    def handler(request):
        nonlocal token_calls, data_calls
        if "openid-connect/token" in str(request.url):
            token_calls += 1
            return httpx.Response(200, json=token_response(f"token-{token_calls}"))
        data_calls += 1
        if data_calls == 1:
            assert request.headers["authorization"] == "Bearer token-1"
            return httpx.Response(401, json={"message": "expired"})
        assert request.headers["authorization"] == "Bearer token-2"
        return httpx.Response(200, json=parking_response("CarParks", []))

    client = make_client(handler)

    list(client.iter_pages(TDXDataset.CAR_PARKS))

    assert token_calls == 2
    assert data_calls == 2


def test_client_retries_server_errors_but_bounds_attempts():
    calls = 0

    def handler(request):
        nonlocal calls
        if "openid-connect/token" in str(request.url):
            return httpx.Response(200, json=token_response())
        calls += 1
        return httpx.Response(503, json={"message": "unavailable"})

    client = make_client(handler, max_attempts=3)

    with pytest.raises(TDXRequestError, match="HTTP 503") as error:
        list(client.iter_pages(TDXDataset.CAR_PARKS))

    assert calls == 3
    assert error.value.status_code == 503


def test_client_does_not_retry_permanent_client_errors():
    calls = 0

    def handler(request):
        nonlocal calls
        if "openid-connect/token" in str(request.url):
            return httpx.Response(200, json=token_response())
        calls += 1
        return httpx.Response(400, json={"message": "bad query"})

    client = make_client(handler)

    with pytest.raises(TDXRequestError, match="HTTP 400"):
        list(client.iter_pages(TDXDataset.CAR_PARKS))

    assert calls == 1


def test_client_rejects_incomplete_pagination():
    def handler(request):
        if "openid-connect/token" in str(request.url):
            return httpx.Response(200, json=token_response())
        offset = int(request.url.params["$skip"])
        records = [{"CarParkID": "one"}] if offset == 0 else []
        return httpx.Response(200, json=parking_response("CarParks", records, count=2))

    client = make_client(handler)

    with pytest.raises(TDXResponseError, match="stopped at 1 of 2"):
        list(client.iter_pages(TDXDataset.CAR_PARKS))


def test_client_rejects_wrapper_schema_drift():
    def handler(request):
        if "openid-connect/token" in str(request.url):
            return httpx.Response(200, json=token_response())
        payload = parking_response("CarParks", [])
        payload["NewEnvelopeField"] = True
        return httpx.Response(200, json=payload)

    client = make_client(handler)

    with pytest.raises(TDXResponseError, match="NewEnvelopeField"):
        list(client.iter_pages(TDXDataset.CAR_PARKS))


def test_invalid_token_response_never_exposes_credentials():
    def handler(_request):
        return httpx.Response(200, json={"error": "no token"})

    client = make_client(handler)

    with pytest.raises(TDXAuthenticationError) as error:
        list(client.iter_pages(TDXDataset.CAR_PARKS))

    assert "client-id" not in str(error.value)
    assert "client-secret" not in str(error.value)
