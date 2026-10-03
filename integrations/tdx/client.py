"""HTTP client for the authenticated, paginated TDX Parking v1 API."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from time import monotonic, sleep
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from parking.exceptions import IngestionClientError, IngestionResponseError

from .schemas import TDXParkingWrapper

TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
BASE_URL = "https://tdx.transportdata.tw/api/basic"


class TDXDataset(StrEnum):
    CAR_PARKS = "car_parks"
    PARKING_ENTRANCE_EXITS = "parking_entrance_exits"
    OFF_STREET_SPOTS = "off_street_spots"
    PARKING_SEGMENTS = "parking_segments"
    ON_STREET_SPOTS = "on_street_spots"


@dataclass(frozen=True)
class DatasetSpec:
    path: str
    records_key: str
    order_by: str


DATASET_SPECS = {
    TDXDataset.CAR_PARKS: DatasetSpec(
        "/v1/Parking/OffStreet/CarPark/City/{city}",
        "CarParks",
        "CarParkID",
    ),
    TDXDataset.PARKING_ENTRANCE_EXITS: DatasetSpec(
        "/v1/Parking/OffStreet/ParkingEntranceExit/City/{city}",
        "ParkingEntranceExits",
        "CarParkID",
    ),
    TDXDataset.OFF_STREET_SPOTS: DatasetSpec(
        "/v1/Parking/OffStreet/ParkingSpot/City/{city}",
        "ParkingSpots",
        "CarParkID",
    ),
    TDXDataset.PARKING_SEGMENTS: DatasetSpec(
        "/v1/Parking/OnStreet/ParkingSegment/City/{city}",
        "ParkingSegments",
        "ParkingSegmentID",
    ),
    TDXDataset.ON_STREET_SPOTS: DatasetSpec(
        "/v1/Parking/OnStreet/ParkingSpot/City/{city}",
        "ParkingSegmentSpots",
        "ParkingSegmentID,ParkingSpotID,Position/PositionLon,Position/PositionLat",
    ),
}


class TDXClientError(IngestionClientError):
    """Base error with messages safe to persist in sync summaries."""


class TDXConfigurationError(TDXClientError):
    pass


class TDXAuthenticationError(TDXClientError):
    pass


class TDXRequestError(TDXClientError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TDXResponseError(TDXClientError, IngestionResponseError):
    pass


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    access_token: str = Field(min_length=1)
    expires_in: int = Field(gt=0)
    token_type: str


@dataclass(frozen=True)
class TDXPage:
    dataset: TDXDataset
    metadata: TDXParkingWrapper
    records: list[dict[str, Any]]
    offset: int


class TDXClient:
    METADATA_KEYS = {
        "SrcUpdateTime",
        "SrcUpdateInterval",
        "UpdateTime",
        "UpdateInterval",
        "AuthorityCode",
        "VersionID",
        "Count",
    }

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        http_client: httpx.Client | None = None,
        base_url: str = BASE_URL,
        token_url: str = TOKEN_URL,
        timeout_seconds: float = 30,
        page_size: int = 500,
        max_attempts: int = 4,
        backoff_seconds: float = 1,
        max_retry_delay_seconds: float = 60,
        sleeper: Callable[[float], None] = sleep,
        clock: Callable[[], float] = monotonic,
        jitter: Callable[[], float] = lambda: 0.5,
    ):
        if not client_id or not client_secret:
            raise TDXConfigurationError("TDX client credentials are required")
        if page_size <= 0 or max_attempts <= 0:
            raise TDXConfigurationError("TDX page size and max attempts must be positive")

        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url
        self.page_size = page_size
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_retry_delay_seconds = max_retry_delay_seconds
        self.sleeper = sleeper
        self.clock = clock
        self.jitter = jitter
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)
        self._owns_http_client = http_client is None
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def close(self):
        if self._owns_http_client:
            self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def iter_pages(self, dataset: TDXDataset, *, city: str = "Tainan") -> Iterator[TDXPage]:
        spec = DATASET_SPECS[dataset]
        offset = 0
        expected_count: int | None = None
        expected_snapshot: tuple[int, datetime] | None = None

        while True:
            response = self._request(
                "GET",
                f"{self.base_url}{spec.path.format(city=city)}",
                authenticated=True,
                params={
                    "$top": self.page_size,
                    "$skip": offset,
                    "$count": "true",
                    "$format": "JSON",
                    "$orderby": spec.order_by,
                },
            )
            payload = self._json_object(response, context=dataset.value)
            page = self._parse_page(dataset, spec, payload, offset)

            if expected_count is None:
                expected_count = page.metadata.count
            elif page.metadata.count != expected_count:
                raise TDXResponseError(
                    f"{dataset.value} Count changed during pagination: "
                    f"{expected_count} -> {page.metadata.count}"
                )

            snapshot = (page.metadata.version_id, page.metadata.source_updated_at)
            if expected_snapshot is None:
                expected_snapshot = snapshot
            elif snapshot != expected_snapshot:
                raise TDXResponseError(f"{dataset.value} source snapshot changed during pagination")

            yield page
            offset += len(page.records)

            if expected_count is None:
                raise TDXResponseError(f"{dataset.value} response omitted Count")
            if offset >= expected_count:
                if offset != expected_count:
                    raise TDXResponseError(
                        f"{dataset.value} returned {offset} records for Count={expected_count}"
                    )
                return
            if not page.records:
                raise TDXResponseError(
                    f"{dataset.value} pagination stopped at {offset} of {expected_count} records"
                )

    def _parse_page(
        self,
        dataset: TDXDataset,
        spec: DatasetSpec,
        payload: dict[str, Any],
        offset: int,
    ) -> TDXPage:
        unexpected_keys = set(payload) - self.METADATA_KEYS - {spec.records_key}
        if unexpected_keys:
            raise TDXResponseError(
                f"{dataset.value} wrapper contains unexpected fields: {sorted(unexpected_keys)}"
            )

        if spec.records_key not in payload or not isinstance(payload[spec.records_key], list):
            raise TDXResponseError(
                f"{dataset.value} response omitted list field {spec.records_key}"
            )

        try:
            metadata = TDXParkingWrapper.model_validate(
                {key: payload[key] for key in self.METADATA_KEYS if key in payload}
            )
        except ValidationError as error:
            raise TDXResponseError(f"{dataset.value} wrapper validation failed: {error}") from error

        records = payload[spec.records_key]
        if not all(isinstance(record, dict) for record in records):
            raise TDXResponseError(f"{dataset.value} records must be JSON objects")
        return TDXPage(dataset=dataset, metadata=metadata, records=records, offset=offset)

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh and self._access_token and self.clock() < self._token_expires_at - 60:
            return self._access_token

        response = self._request(
            "POST",
            self.token_url,
            authenticated=False,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        try:
            token = TokenResponse.model_validate(self._json_object(response, context="token"))
        except ValidationError as error:
            raise TDXAuthenticationError("TDX token response was invalid") from error
        if token.token_type.lower() != "bearer":
            raise TDXAuthenticationError("TDX token response used an unsupported token type")

        self._access_token = token.access_token
        self._token_expires_at = self.clock() + token.expires_in
        return token.access_token

    def _request(
        self,
        method: str,
        url: str,
        *,
        authenticated: bool,
        **kwargs,
    ) -> httpx.Response:
        refreshed_after_unauthorized = False
        for attempt in range(1, self.max_attempts + 1):
            headers = dict(kwargs.pop("headers", {}))
            if authenticated:
                headers["authorization"] = f"Bearer {self._get_access_token()}"
            try:
                response = self.http_client.request(method, url, headers=headers, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == self.max_attempts:
                    raise TDXRequestError(
                        f"TDX request failed after {attempt} attempts: {type(error).__name__}"
                    ) from error
                self.sleeper(self._retry_delay(attempt, None))
                continue

            if response.status_code == 401 and authenticated and not refreshed_after_unauthorized:
                self._access_token = None
                self._token_expires_at = 0
                refreshed_after_unauthorized = True
                if attempt < self.max_attempts:
                    continue

            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self.max_attempts:
                self.sleeper(self._retry_delay(attempt, response))
                continue
            if response.is_error:
                error_type = TDXAuthenticationError if not authenticated else TDXRequestError
                raise error_type(
                    f"TDX request returned HTTP {response.status_code}",
                    **({"status_code": response.status_code} if authenticated else {}),
                )
            return response

        raise AssertionError("TDX retry loop exited unexpectedly")

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0), self.max_retry_delay_seconds)
                except ValueError:
                    pass
        delay = self.backoff_seconds * (2 ** (attempt - 1)) + max(self.jitter(), 0)
        return min(delay, self.max_retry_delay_seconds)

    @staticmethod
    def _json_object(response: httpx.Response, *, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise TDXResponseError(f"TDX {context} response was not valid JSON") from error
        if not isinstance(payload, dict):
            raise TDXResponseError(f"TDX {context} response must be a JSON object")
        return payload
