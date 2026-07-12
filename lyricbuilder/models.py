"""Shared data structures."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


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
