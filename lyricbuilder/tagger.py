"""Write .lrc files and embed lyrics into audio tags. Sole side-effect module."""
from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.id3 import USLT, ID3
from mutagen.mp4 import MP4

from .models import Clue, LyricResult

EMBED_SUPPORTED = {"mp3", "m4a", "aac", "alac", "flac", "aiff"}


class Tagger:
    def __init__(self, dry_run: bool = False, force: bool = False, embed: bool = True, lrc: bool = True):
        self.dry_run = dry_run
        self.force = force
        self.embed = embed
        self.lrc = lrc

    def apply(self, clue: Clue, result: LyricResult) -> dict:
        out = {"lrc": "skipped", "embed": "skipped"}
        if not result.matched or result.text is None:
            return out
        if self.dry_run:
            return out
        out["lrc"] = self._write_lrc(clue, result.text)
        out["embed"] = self._embed(clue, result.text)
        return out

    def _write_lrc(self, clue: Clue, text: str) -> str:
        if not self.lrc:
            return "skipped"
        path = clue.path.with_suffix(".lrc")
        if path.exists() and not self.force:
            return "skipped"
        try:
            path.write_text(text, encoding="utf-8")
            return "written"
        except OSError:
            return "failed"

    def _embed(self, clue: Clue, text: str) -> str:
        if not self.embed:
            return "skipped"
        if clue.fmt not in EMBED_SUPPORTED:
            return "unsupported"
        try:
            if clue.fmt == "mp3":
                return self._embed_mp3(clue.path, text)
            if clue.fmt in {"m4a", "aac", "alac"}:
                return self._embed_mp4(clue.path, text)
            if clue.fmt == "flac":
                return self._embed_flac(clue.path, text)
            if clue.fmt == "aiff":
                return self._embed_aiff(clue.path, text)
        except Exception:
            return "failed"
        return "failed"

    @staticmethod
    def _embed_mp3(path: Path, text: str) -> str:
        try:
            tags = ID3(path)
        except Exception:
            tags = ID3()
        tags.setall("USLT", [USLT(encoding=3, lang="chi", desc="", text=text)])
        tags.save(path)
        return "written"

    @staticmethod
    def _embed_mp4(path: Path, text: str) -> str:
        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9lyr"] = text
        audio.save()
        return "written"

    @staticmethod
    def _embed_flac(path: Path, text: str) -> str:
        audio = MutagenFile(path)
        audio["lyrics"] = text
        audio.save()
        return "written"

    @staticmethod
    def _embed_aiff(path: Path, text: str) -> str:
        a = AIFF(path)
        if a.tags is None:
            a.add_tags()
        a.tags.setall("USLT", [USLT(encoding=3, lang="chi", desc="", text=text)])
        a.save()
        return "written"
