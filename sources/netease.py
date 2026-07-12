"""NetEase Cloud Music lyric source."""
from __future__ import annotations

import time
import httpx

from lyricbuilder.models import LyricResult, TransientSourceError

SEARCH_URL = "https://music.163.com/api/search/get"
LYRIC_URL = "https://music.163.com/api/song/lyric"


class NeteaseSource:
    name = "netease"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 2):
        self._client = client or httpx.Client(timeout=timeout, headers={"Referer": "https://music.163.com"}, trust_env=False)
        self._retries = retries

    def get(self, title: str | None, artist: str | None) -> LyricResult:
        query = {"title": title, "artist": artist}
        if not title:
            return LyricResult(False, None, None, self.name, query)
        song_id = self._search(title, artist)
        if not song_id:
            return LyricResult(False, None, None, self.name, query)
        lyric = self._fetch_lyric(song_id)
        if not lyric:
            return LyricResult(False, None, None, self.name, query)
        rtype = "lrc" if _has_timestamps(lyric) else "plain"
        return LyricResult(True, rtype, lyric, self.name, query)

    def _search(self, title: str, artist: str | None) -> str | None:
        """Returns song_id on hit, None on confirmed miss (200 with empty results).

        Raises TransientSourceError on timeout / 429-after-retries / 5xx / bad JSON
        / connection error — must NOT be negative-cached.
        """
        term = f"{title} {artist}" if artist else title
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(SEARCH_URL, params={"s": term, "type": 1, "limit": 5})
            except httpx.HTTPError as e:
                raise TransientSourceError("netease search failed") from e
            if resp.status_code == 200:
                try:
                    songs = resp.json().get("result", {}).get("songs", [])
                except ValueError as e:
                    raise TransientSourceError("netease search bad JSON") from e
                return str(songs[0]["id"]) if songs else None  # empty = confirmed miss
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt)); continue
            raise TransientSourceError(f"netease search status {resp.status_code}")
        raise TransientSourceError("netease search 429 retries exhausted")

    def _fetch_lyric(self, song_id: str) -> str | None:
        """Returns lyric text on hit, None on confirmed miss (200 with no lrc).

        Raises TransientSourceError on timeout / 429-after-retries / 5xx / bad JSON
        / connection error — must NOT be negative-cached.
        """
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(LYRIC_URL, params={"id": song_id, "lv": 1, "tv": -1})
            except httpx.HTTPError as e:
                raise TransientSourceError("netease lyric fetch failed") from e
            if resp.status_code == 200:
                try:
                    return (resp.json().get("lrc") or {}).get("lyric")  # None = confirmed no-lyric
                except ValueError as e:
                    raise TransientSourceError("netease lyric bad JSON") from e
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt)); continue
            raise TransientSourceError(f"netease lyric status {resp.status_code}")
        raise TransientSourceError("netease lyric 429 retries exhausted")


def _has_timestamps(text: str) -> bool:
    import re
    return bool(re.search(r"\[\d{2}:\d{2}", text or ""))
