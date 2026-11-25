"""Per-host request pacing (the noise governor).

Platforms rate-limit and ban noisy clients. Every connector request goes
through here: a minimum interval per host, a cap on in-flight requests per
host, and exponential backoff when the host answers 429/503.
"""

from __future__ import annotations

import asyncio
import random
import time
from urllib.parse import urlparse

import httpx

PROFILES = {
    "quiet": {"interval": 3.0, "inflight": 1},
    "balanced": {"interval": 1.2, "inflight": 2},
    "aggressive": {"interval": 0.4, "inflight": 4},
}

USER_AGENT = "leadscout/0.1 (market research; contact via repository)"


class Governor:
    def __init__(self, profile: str = "balanced", user_agent: str = USER_AGENT):
        p = PROFILES.get(profile, PROFILES["balanced"])
        self.interval = p["interval"]
        self.inflight = p["inflight"]
        self._last: dict[str, float] = {}
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": user_agent})

    def _host(self, url: str) -> str:
        return urlparse(url).hostname or url

    async def request(self, method: str, url: str, **kw) -> httpx.Response:
        host = self._host(url)
        sem = self._sems.setdefault(host, asyncio.Semaphore(self.inflight))
        lock = self._locks.setdefault(host, asyncio.Lock())
        backoff = 2.0
        for attempt in range(4):
            async with sem:
                async with lock:
                    wait = self._last.get(host, 0) + self.interval - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait + random.uniform(0, self.interval * 0.3))
                    self._last[host] = time.monotonic()
                resp = await self.client.request(method, url, **kw)
            if resp.status_code in (429, 503) and attempt < 3:
                retry_after = resp.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                await asyncio.sleep(min(delay, 60))
                backoff *= 2
                continue
            return resp
        return resp

    async def get(self, url: str, **kw) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:
        return await self.request("POST", url, **kw)

    async def aclose(self) -> None:
        await self.client.aclose()
