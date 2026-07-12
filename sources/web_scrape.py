"""Web-scrape fallback lyric source. Returns plain text only."""
from __future__ import annotations

import time
import httpx
from bs4 import BeautifulSoup

from lyricbuilder.models import LyricResult


class WebScrapeSource:
    name = "scrape"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 1):
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "lyricbuilder/0.1"}, trust_env=False)
        self._retries = retries

    def get(self, title: str | None, artist: str | None) -> LyricResult:
        query = {"title": title, "artist": artist}
        if not title:
            return LyricResult(False, None, None, self.name, query)
        html = self._fetch(title, artist)
        if not html:
            return LyricResult(False, None, None, self.name, query)
        text = self._parse(html)
        if not text:
            return LyricResult(False, None, None, self.name, query)
        return LyricResult(True, "plain", text, self.name, query)

    def _fetch(self, title: str, artist: str | None) -> str | None:
        url = f"https://example-lyrics.test/search?q={title}"
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(url)
            except httpx.HTTPError:
                return None
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt)); continue
            return None
        return None

    @staticmethod
    def _parse(html: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        for sel in (".lyrics", ".lyric", "#lyric", ".lrc"):
            node = soup.select_one(sel)
            if node:
                lines = [p.get_text(strip=True) for p in node.find_all(["p", "br"]) if p.get_text(strip=True)]
                if not lines:
                    lines = [node.get_text("\n", strip=True)]
                text = "\n".join(lines)
                if text:
                    return text
        return None
