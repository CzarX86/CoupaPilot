from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from typing import Mapping

import httpx

from src.auth.models import AuthState, SessionCheck
from src.engine.tls import system_ssl_context

COUPA_URL = "https://unilever.coupahost.com"
AUTH_REDIRECT_MARKERS = ("/login", "/oauth", "/sso", "/authorization", "openid", "pingfederate")


class SessionValidator:
    """Validate a Coupa cookie jar with one bounded HTTP request."""

    def __init__(self, base_url: str = COUPA_URL, timeout: float = 10.0, attempts: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.attempts = max(1, int(attempts))

    @staticmethod
    def _is_coupa_host(url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower().rstrip(".")
        return hostname == "coupahost.com" or hostname.endswith(".coupahost.com")

    @staticmethod
    def _is_auth_redirect(url: str) -> bool:
        lowered = url.lower()
        return any(marker in lowered for marker in AUTH_REDIRECT_MARKERS)

    async def validate(self, cookies: Mapping[str, str] | None) -> SessionCheck:
        normalised = {str(key): str(value) for key, value in (cookies or {}).items() if value is not None}
        if not normalised.get("_coupa_session"):
            return SessionCheck(AuthState.MISSING, "No cached Coupa session.", normalised, "none")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        cookie_jar = httpx.Cookies()
        cookie_domain = urlparse(self.base_url).hostname or ""
        for name, value in normalised.items():
            cookie_jar.set(name, value, domain=cookie_domain, path="/")
        for attempt in range(self.attempts):
            try:
                async with httpx.AsyncClient(
                    cookies=cookie_jar,
                    headers=headers,
                    follow_redirects=True,
                    timeout=self.timeout,
                    verify=system_ssl_context(),
                ) as client:
                    response = await client.get(f"{self.base_url}/order_headers")
                    cookie_jar = client.cookies
                    refreshed = {
                        str(cookie.name): str(cookie.value)
                        for cookie in cookie_jar.jar
                    } or normalised
                final_url = str(response.url)
                if response.status_code == 200 and self._is_coupa_host(final_url) and not self._is_auth_redirect(final_url):
                    return SessionCheck(AuthState.VALID, "Cached Coupa session is valid.", refreshed, "cache")
                if response.status_code in {401, 403} or self._is_auth_redirect(final_url):
                    if attempt + 1 < self.attempts:
                        await asyncio.sleep(0.25)
                        continue
                    return SessionCheck(AuthState.EXPIRED, "Cached Coupa session expired.", refreshed, "cache")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.attempts:
                        await asyncio.sleep(0.25)
                        continue
                    return SessionCheck(AuthState.UNAVAILABLE, "Coupa is temporarily unavailable or rate limited.", refreshed, "cache")
                else:
                    return SessionCheck(AuthState.EXPIRED, "Coupa rejected the cached session.", refreshed, "cache")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                pass
            except Exception as exc:
                return SessionCheck(AuthState.UNAVAILABLE, f"Could not verify the cached session: {exc}", normalised, "cache")
            if attempt + 1 < self.attempts:
                await asyncio.sleep(0.25)

        return SessionCheck(
            AuthState.UNAVAILABLE,
            "Could not verify the cached session because Coupa or the network is unavailable.",
            normalised,
            "cache",
        )
