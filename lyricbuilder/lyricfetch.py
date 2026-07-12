"""Lyric-fetching pipeline: cache-first, sources-in-priority, negative caching."""
from __future__ import annotations

from .models import Clue, LyricResult
from .cache import Cache


class LyricFetcher:
    def __init__(self, sources: list, cache: Cache | None = None):
        self._sources = sources
        self._cache = cache

    def fetch(self, clue: Clue) -> LyricResult:
        query = {"title": clue.title, "artist": clue.artist}
        if not clue.title and not clue.artist:
            return LyricResult(False, None, None, None, query)
        if self._cache is not None:
            cached = self._cache.get(clue.title or "", clue.artist or "")
            if cached is not None:
                return _from_cache_dict(cached, query)
        result = LyricResult(False, None, None, None, query)
        for src in self._sources:
            try:
                r = src.get(clue.title, clue.artist)
            except Exception:
                r = LyricResult(False, None, None, getattr(src, "name", "?"), query)
            if r.matched:
                result = r
                break
        if self._cache is not None:
            self._cache.put(clue.title or "", clue.artist or "", _to_cache_dict(result))
        return result


def _to_cache_dict(r: LyricResult) -> dict:
    return {"matched": r.matched, "type": r.type, "text": r.text, "source": r.source}


def _from_cache_dict(d: dict, query: dict) -> LyricResult:
    return LyricResult(d.get("matched"), d.get("type"), d.get("text"), d.get("source"), query)
