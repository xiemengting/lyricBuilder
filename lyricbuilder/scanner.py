"""Scan a music directory and extract per-file clues for lyric matching."""
from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3

from .models import Clue

DEFAULT_EXTS = [".mp3", ".m4a", ".aac", ".alac", ".flac", ".wav", ".aiff"]

_DASH_SPLIT = re.compile(r"\s*[-－—]\s*")


def _parse_filename(stem: str) -> tuple[str | None, str | None]:
    parts = _DASH_SPLIT.split(stem, maxsplit=1)
    if len(parts) == 2:
        a, b = parts[0].strip(), parts[1].strip()
        # "artist - title" is the dominant convention
        return b, a
    return None, None


class Scanner:
    def __init__(self, music_dir: Path, exts: list[str] | None = None):
        self.music_dir = Path(music_dir).expanduser()
        self.exts = exts or DEFAULT_EXTS

    def scan(self) -> list[Clue]:
        clues: list[Clue] = []
        for p in sorted(self.music_dir.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in self.exts:
                continue
            clues.append(self._clue_for(p))
        return clues

    def _clue_for(self, path: Path) -> Clue:
        fmt = path.suffix.lower().lstrip(".")
        title, artist, source = self._from_tags(path)
        if not title and not artist:
            title, artist = _parse_filename(path.stem)
            source = "filename" if (title or artist) else "none"
        return Clue(path=path, fmt=fmt, title=title, artist=artist, source=source)

    @staticmethod
    def _from_tags(path: Path) -> tuple[str | None, str | None, str]:
        # Primary path: a real audio container mutagen can parse.
        try:
            mf = MutagenFile(path, easy=True)
        except Exception:
            mf = None
        if mf is not None:
            title = mf.get("title", [None])[0]
            artist = mf.get("artist", [None])[0]
            if title or artist:
                return title, artist, "tag"
        # Fallback for .mp3 files that carry an ID3 block but no MPEG
        # audio data (e.g. fixtures or truncated files): read ID3 directly.
        if path.suffix.lower() == ".mp3":
            try:
                tags = ID3(path)
            except Exception:
                return None, None, "none"
            title = artist = None
            tit2 = tags.getall("TIT2")
            tpe1 = tags.getall("TPE1")
            if tit2 and tit2[0].text:
                title = tit2[0].text[0]
            if tpe1 and tpe1[0].text:
                artist = tpe1[0].text[0]
            if title or artist:
                return title, artist, "tag"
        elif path.suffix.lower() == ".aiff":
            # AIFF stores ID3 in an ID3 chunk; MutagenFile(easy=True) does
            # not surface them as easy keys, so read frames via mutagen.aiff.
            try:
                from mutagen.aiff import AIFF
                tags = AIFF(path).tags
            except Exception:
                return None, None, "none"
            title = artist = None
            if tags is not None:
                tit2 = tags.getall("TIT2")
                tpe1 = tags.getall("TPE1")
                if tit2 and tit2[0].text:
                    title = tit2[0].text[0]
                if tpe1 and tpe1[0].text:
                    artist = tpe1[0].text[0]
            if title or artist:
                return title, artist, "tag"
        return None, None, "none"
