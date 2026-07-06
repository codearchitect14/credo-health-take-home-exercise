import logging
from typing import Any, Iterator
from urllib.parse import urljoin

import requests
from django.conf import settings
from requests.exceptions import ConnectionError, HTTPError, Timeout
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FhirClientError(Exception):
    """Raised when the FHIR API returns a non-retryable or exhausted error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RetryableFhirError(FhirClientError):
    """Transient upstream failure (429/5xx); retried with backoff before surfacing."""


class FhirClient:
    """Thin client for the HAPI FHIR R4 sandbox with retry/backoff."""

    def __init__(self, base_url: str | None = None, session: requests.Session | None = None):
        self.base_url = (base_url or settings.FHIR_BASE_URL).rstrip("/") + "/"
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/fhir+json"})

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    @retry(
        retry=retry_if_exception_type((ConnectionError, Timeout, RetryableFhirError)),
        stop=stop_after_attempt(settings.FHIR_MAX_RETRIES),
        wait=wait_exponential_jitter(initial=1, max=16),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        """GET a URL with retry/backoff on transient failures."""
        try:
            response = self.session.get(
                url, params=params, timeout=settings.FHIR_REQUEST_TIMEOUT
            )
        except (ConnectionError, Timeout) as exc:
            logger.warning("FHIR request failed (network): %s %s", url, exc)
            raise

        if response.status_code in RETRYABLE_STATUS_CODES:
            logger.warning(
                "FHIR request retryable status %s: %s", response.status_code, url
            )
            raise RetryableFhirError(
                f"Retryable FHIR error: {response.status_code}",
                status_code=response.status_code,
            )

        try:
            response.raise_for_status()
        except HTTPError as exc:
            raise FhirClientError(
                f"FHIR request failed: {response.status_code}",
                status_code=response.status_code,
            ) from exc

        return response.json()

    def iter_bundle_pages(
        self, path: str, params: dict | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield each page of a FHIR Bundle, following 'next' links."""
        data = self._get(self._url(path), params=params)
        yield data

        while True:
            next_url = None
            for link in data.get("link", []):
                if link.get("relation") == "next":
                    next_url = link.get("url")
                    break
            if not next_url:
                break
            data = self._get(next_url)
            yield data

    def fetch_patients(self, count: int | None = None) -> Iterator[dict[str, Any]]:
        params = {"_count": count or settings.FHIR_PAGE_SIZE}
        for bundle in self.iter_bundle_pages("Patient", params=params):
            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if resource and resource.get("resourceType") == "Patient":
                    yield resource

    def fetch_observations_for_patient(
        self, patient_fhir_id: str, count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        params = {
            "patient": patient_fhir_id,
            "_count": count or settings.FHIR_PAGE_SIZE,
        }
        for bundle in self.iter_bundle_pages("Observation", params=params):
            for entry in bundle.get("entry", []):
                resource = entry.get("resource")
                if resource and resource.get("resourceType") == "Observation":
                    yield resource
