"""Async HTTP client for Flashscore's feed host, GraphQL host and HTML pages.

* **Text feeds** on `global.flashscore.ninja` -- a match's incidents
  (`df_sui_`), statistics (`df_st_`), box score (`df_psn_`), missing players,
  commentary and head-to-head, plus the league and team match lists used to
  find matches. They need one header, `x-fsign`, which the site embeds in
  every page as `"feed_sign":"..."`. A missing or stale value is answered
  with **HTTP 401**, the trigger for re-reading it.
* **Persisted GraphQL queries** on `2.ds.lsapp.eu` -- lineups (`dlie2`),
  football player stats (`epmsd` + `epmsse`) and momentum (`mmts`). No
  headers or cookies.
* **HTML pages** on `www.flashscore.com` -- the match page (header and the
  list of tabs the match has), league and team pages. `www` refuses a plain
  TLS client at the handshake, hence the Chrome-impersonating session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Awaitable, Callable

from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

ProxyFallback = Callable[[], Awaitable[str | None]]

SITE_URL = "https://www.flashscore.com"
FEED_URL = "https://global.flashscore.ninja/2/x/feed/"
GRAPHQL_URL = "https://2.ds.lsapp.eu/pq_graphql"

PROJECT_ID = 2

# Verified 2026-09-28. One value for every sport; replaced automatically on
# the first 401 (`_refresh_sign`).
DEFAULT_FEED_SIGN = "SW9D1eZo"

# A long-lived match page that carries the current `feed_sign`.
SIGN_SOURCE_PATH = "/match/MNThRu6l/"
_FEED_SIGN_RE = re.compile(r'"feed_sign"\s*:\s*"(\w+)"')

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_URL}/",
    "Origin": SITE_URL,
}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BLOCKED_STATUS = {403}


class FlashscoreError(RuntimeError):
    """A Flashscore request failed after retries."""

    def __init__(self, url: str, status_code: int, detail: str) -> None:
        super().__init__(f"Flashscore request failed ({status_code}) for {url}: {detail}")
        self.url = url
        self.status_code = status_code


class FlashscoreNotFoundError(FlashscoreError):
    """The requested page or match does not exist."""

    def __init__(self, url: str) -> None:
        super().__init__(url, 404, "not found")


class FlashscoreClient:
    """Direct HTTP client -- no browser."""

    def __init__(
        self,
        *,
        proxy: str | None = None,
        proxy_fallback: ProxyFallback | None = None,
        feed_sign: str = DEFAULT_FEED_SIGN,
        max_retries: int = 4,
        max_escalations: int = 8,
        request_delay: float = 0.3,
        timeout: int = 30,
    ) -> None:
        self._session = AsyncSession(impersonate="chrome")
        self._proxy = proxy
        self._proxy_fallback = proxy_fallback
        self._feed_sign = feed_sign
        self._max_retries = max_retries
        self._max_escalations = max_escalations
        self._request_delay = request_delay
        self._timeout = timeout
        self._proxy_lock = asyncio.Lock()
        self._sign_lock = asyncio.Lock()
        self.escalations_used = 0
        self.sign_refreshes = 0
        self.requests = 0

    async def close(self) -> None:
        await self._session.close()

    async def __aenter__(self) -> FlashscoreClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ---- public endpoints -------------------------------------------------

    async def feed(self, name: str) -> str:
        """Any text feed by name. An empty or `0` body means "nothing there"."""
        url = FEED_URL + name
        for attempt in range(2):
            sign = self._feed_sign
            status, text = await self._request(url, headers={**DEFAULT_HEADERS, "x-fsign": sign})
            if status == 200:
                return text
            if status == 404:
                raise FlashscoreNotFoundError(url)
            if status == 401 and attempt == 0:
                await self._refresh_sign(sign)
                continue
            raise FlashscoreError(url, status, text[:200])
        raise FlashscoreError(url, 401, "x-fsign rejected even after re-reading it")

    async def page(self, path_or_url: str) -> str:
        """An HTML page on www.flashscore.com."""
        url = path_or_url if path_or_url.startswith("http") else SITE_URL + path_or_url
        status, text = await self._request(url, headers=DEFAULT_HEADERS)
        if status == 404:
            raise FlashscoreNotFoundError(url)
        if status != 200:
            raise FlashscoreError(url, status, text[:200])
        return text

    async def graphql(self, query_hash: str, **params: Any) -> dict[str, Any] | None:
        """A persisted GraphQL query's `data` object.

        A match without that data answers 200 with `"errors"` and a null
        `data`, or 400 (`dts` on sports without typed stats); both are None.
        """
        query = {"_hash": query_hash, **{k: str(v) for k, v in params.items()}}
        status, text = await self._request(GRAPHQL_URL, params=query, headers=DEFAULT_HEADERS)
        if status in (400, 404):
            return None
        if status != 200:
            raise FlashscoreError(GRAPHQL_URL, status, text[:200])
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise FlashscoreError(GRAPHQL_URL, status, f"expected JSON, got {text[:120]!r}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, dict) else None

    # ---- feed signing -----------------------------------------------------

    async def _refresh_sign(self, rejected: str) -> None:
        async with self._sign_lock:
            if self._feed_sign != rejected:
                return
            page = await self.page(SIGN_SOURCE_PATH)
            match = _FEED_SIGN_RE.search(page)
            if not match:
                raise FlashscoreError(
                    FEED_URL, 401, "x-fsign was rejected and no feed_sign was found on a match page"
                )
            logger.warning(f"Flashscore rotated its feed signature; now using {match.group(1)}.")
            self._feed_sign = match.group(1)
            self.sign_refreshes += 1

    # ---- transport --------------------------------------------------------

    async def _rotate_proxy(self, proxy_in_use: str | None) -> bool:
        if self._proxy_fallback is None:
            return False
        if self.escalations_used >= self._max_escalations:
            logger.warning(f"Giving up after {self.escalations_used} proxy IP(s).")
            return False
        async with self._proxy_lock:
            if self._proxy != proxy_in_use:
                return True
            new_proxy = await self._proxy_fallback()
            if not new_proxy:
                return False
            self._proxy = new_proxy
            self.escalations_used += 1
            return True

    async def _request(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str],
    ) -> tuple[int, str]:
        """GET with retries. Returns every definitive status to the caller."""
        last_exc: Exception | None = None
        attempt = 0
        while attempt <= self._max_retries:
            escalated = False
            proxy_in_use = self._proxy
            try:
                self.requests += 1
                resp = await self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    proxy=proxy_in_use,
                    timeout=self._timeout,
                    allow_redirects=True,
                )
            except Exception as exc:  # noqa: BLE001 - DNS, timeout, a refused proxy CONNECT
                last_exc = FlashscoreError(url, 0, repr(exc))
                if proxy_in_use is not None:
                    escalated = await self._rotate_proxy(proxy_in_use)
            else:
                status = resp.status_code
                if status in BLOCKED_STATUS:
                    last_exc = FlashscoreError(url, status, "blocked")
                    logger.warning(f"Flashscore answered {status} for {url}")
                    escalated = await self._rotate_proxy(proxy_in_use)
                elif status in RETRYABLE_STATUS:
                    last_exc = FlashscoreError(url, status, resp.text[:200])
                else:
                    return status, resp.text

            if escalated:
                continue
            if attempt < self._max_retries:
                await asyncio.sleep(self._request_delay * (2**attempt))
            attempt += 1

        assert last_exc is not None
        raise last_exc
