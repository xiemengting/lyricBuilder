"""Lyric source protocol."""
from __future__ import annotations
from typing import Protocol
from lyricbuilder.models import LyricResult


class Source(Protocol):
    name: str
    def get(self, title: str | None, artist: str | None) -> LyricResult: ...
