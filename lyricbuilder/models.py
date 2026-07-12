"""Shared data structures."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


class TransientSourceError(Exception):
    """A source failed transiently (timeout / 429-after-retries / 5xx / connection error).

    Distinct from a *confirmed* miss (the source responded and definitively has no
    lyric). Confirmed misses return LyricResult(matched=False) and are cacheable;
    transient failures raise this and must NOT be negative-cached, so a later run
    can retry.
    """


@dataclass
class Clue:
    path: Path
    fmt: str
    title: str | None
    artist: str | None
    source: str  # "tag" | "filename" | "none"


@dataclass
class LyricResult:
    matched: bool
    type: str | None  # "lrc" | "plain" | None
    text: str | None
    source: str | None  # which source produced it
    query: dict  # {title, artist} used to query
