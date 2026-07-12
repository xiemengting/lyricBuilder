"""Lyric-fetching pipeline: cache-first, sources-in-priority, negative caching.

Negative caching is reserved for *confirmed* misses (the source responded and has no
lyric). Transient failures (timeout / 429-after-retries / 5xx / connection error)
raise TransientSourceError and are NOT cached, so a later run can retry — otherwise a
flaky network would poison the cache and a recoverable song would stay unmatched forever.
"""
from __future__ import annotations

from .models import Clue, LyricResult, TransientSourceError
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
        confirmed = False  # did any source give a definitive answer (match OR confirmed miss)?
        for src in self._sources:
            try:
                r = src.get(clue.title, clue.artist)
            except TransientSourceError:
                continue  # flaky — do not treat as a confirmed miss, do not cache
            except Exception:
                continue  # unexpected source error — same: skip, do not cache
            confirmed = True
            if r.matched:
                result = r
                break
        # Only persist to cache when at least one source gave a confirmed answer;
        # if every source failed transiently, leave it uncached so the next run retries.
        if self._cache is not None and confirmed:
            self._cache.put(clue.title or "", clue.artist or "", _to_cache_dict(result))
        return result


def _to_cache_dict(r: LyricResult) -> dict:
    return {"matched": r.matched, "type": r.type, "text": r.text, "source": r.source}


def _from_cache_dict(d: dict, query: dict) -> LyricResult:
    return LyricResult(d.get("matched"), d.get("type"), d.get("text"), d.get("source"), query)
