"""Local result cache for matched lyrics, keyed by normalized title+artist."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s


class Cache:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "index.json"
        self._index = self._load()

    @staticmethod
    def key(title: str, artist: str) -> str:
        raw = f"{_normalize(title)}\x00{_normalize(artist)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _load(self) -> dict:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _save(self) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._index, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)

    def get(self, title: str, artist: str) -> dict | None:
        value = self._index.get(self.key(title, artist))
        return copy.deepcopy(value) if value is not None else None

    def put(self, title: str, artist: str, result: dict) -> None:
        self._index[self.key(title, artist)] = result
        self._save()
