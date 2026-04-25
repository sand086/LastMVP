"""
Routal multi-tenant API client (R00A.3).

Cada cliente LastMile tiene credenciales propias. RoutalClient se instancia por
request via IntegrationService.get_routal_client(client_id).

API key NUNCA aparece en logs (redactada con '***').
"""
import os
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

ROUTAL_BASE_URL = os.environ.get("ROUTAL_BASE_URL", "https://api.routal.com")
ROUTAL_TIMEOUT = float(os.environ.get("ROUTAL_TIMEOUT_SECONDS", "30"))


class RoutalAuthError(Exception):
    """401/403 — invalid api_key or project_id."""


class RoutalNotFoundError(Exception):
    """404 — resource not found."""


class RoutalRateLimitError(Exception):
    """429 — rate limit hit. Caller should backoff."""


class RoutalServiceError(Exception):
    """5xx or unexpected error."""


def _redact(s: Optional[str]) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}***{s[-2:]}"


class RoutalClient:
    def __init__(self, api_key: str, project_id: str, base_url: str = ROUTAL_BASE_URL):
        if not api_key or not project_id:
            raise ValueError("RoutalClient requires both api_key and project_id")
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=ROUTAL_TIMEOUT)

    def _params(self, extra: Optional[dict] = None) -> dict:
        out = {"private_key": self._api_key, "project_id": self._project_id}
        if extra:
            out.update(extra)
        return out

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base_url}{path}"
        # Always merge auth params
        extra = kwargs.pop("params", {}) or {}
        kwargs["params"] = self._params(extra)
        try:
            r = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            logger.warning(f"[routal] timeout {method} {path} key={_redact(self._api_key)}: {e}")
            raise RoutalServiceError(f"Timeout calling Routal: {path}") from e
        except httpx.HTTPError as e:
            logger.warning(f"[routal] network {method} {path} key={_redact(self._api_key)}: {e}")
            raise RoutalServiceError(f"Network error calling Routal: {path}") from e

        if r.status_code in (401, 403):
            raise RoutalAuthError(f"Routal auth failed (HTTP {r.status_code})")
        if r.status_code == 404:
            raise RoutalNotFoundError(f"Routal resource not found: {path}")
        if r.status_code == 429:
            raise RoutalRateLimitError("Routal rate limit hit")
        if r.status_code >= 500:
            raise RoutalServiceError(f"Routal server error: {r.status_code}")
        if r.status_code >= 400:
            # 4xx other → service error, body may help debug
            raise RoutalServiceError(f"Routal {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            return {"raw": r.text}

    async def get_plan(self, plan_id: str) -> dict:
        return await self._request("GET", f"/plans/{plan_id}")

    async def list_plans(self, date: str, page: int = 1, page_size: int = 50) -> list:
        data = await self._request("GET", "/plans", params={"date": date, "page": page, "page_size": page_size})
        # Response shape varies; normalize to list
        if isinstance(data, list):
            return data
        return data.get("data") or data.get("plans") or []

    async def get_plan_stops(self, plan_id: str) -> list:
        data = await self._request("GET", f"/plans/{plan_id}/stops")
        if isinstance(data, list):
            return data
        return data.get("data") or data.get("stops") or []

    async def test_connection(self) -> dict:
        """Light request to validate credentials. Returns {ok, error, latency_ms}."""
        import time
        t0 = time.monotonic()
        try:
            await self._request("GET", "/plans", params={"page_size": 1})
            return {"ok": True, "error": None, "latency_ms": round((time.monotonic() - t0) * 1000)}
        except RoutalAuthError as e:
            return {"ok": False, "error": f"auth: {e}", "latency_ms": round((time.monotonic() - t0) * 1000)}
        except RoutalRateLimitError:
            return {"ok": False, "error": "rate_limit", "latency_ms": round((time.monotonic() - t0) * 1000)}
        except (RoutalNotFoundError, RoutalServiceError) as e:
            return {"ok": False, "error": str(e)[:160], "latency_ms": round((time.monotonic() - t0) * 1000)}

    async def aclose(self):
        await self._client.aclose()
