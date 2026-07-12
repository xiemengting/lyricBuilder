"""LRCLIB source — public, keyless, synced-LRC-focused API."""
from __future__ import annotations

import time
import httpx

from lyricbuilder.models import LyricResult

BASE_URL = "https://lrclib.net/api/get"


class LRCLibSource:
    name = "lrclib"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 2):
        self._client = client or httpx.Client(timeout=timeout)
        self._timeout = timeout
        self._retries = retries

    def get(self, title: str | None, artist: str | None) -> LyricResult:
        query = {"title": title, "artist": artist}
        if not title:
            return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        data = self._request(params)
        if data is None:
            return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)
        synced = data.get("syncedLyrics")
        if synced:
            return LyricResult(matched=True, type="lrc", text=synced, source=self.name, query=query)
        plain = data.get("plainLyrics")
        if plain:
            text = "\n".join(plain) if isinstance(plain, list) else str(plain)
            return LyricResult(matched=True, type="plain", text=text, source=self.name, query=query)
        return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)

    def _request(self, params: dict) -> dict | None:
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(BASE_URL, params=params)
            except httpx.HTTPError:
                return None
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    return None
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            return None
        return None
