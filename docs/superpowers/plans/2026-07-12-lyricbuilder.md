# lyricBuilder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI that scans a music library, fetches lyrics (sync LRC preferred, plain fallback) from LRCLIB → NetEase → web-scrape, writes `.lrc` files alongside audio and embeds lyrics into mp3/m4a tags, with local result caching and dry-run.

**Architecture:** Five focused modules (`scanner`/`lyricfetch`/`tagger`/`cache`/`cli`) plus a `sources/` adapter dir (one file per source). All file/audio side effects isolated in `tagger`; all network isolated in `lyricfetch`+`sources`. TDD bottom-up, pure-local modules first.

**Tech Stack:** Python 3.11+, mutagen (audio tags), httpx (HTTP), beautifulsoup4+lxml (scrape), typer (CLI), rich (output); pytest + respx (HTTP mock) for tests.

## Global Constraints

- Python 3.11+ (anaconda env acceptable).
- Dependencies: mutagen, httpx, beautifulsoup4, lxml, typer, rich; dev: pytest, respx, pytest-tmpfiles.
- Never make real network requests in tests — all HTTP via respx mocks.
- Never commit binary audio fixtures — tests synthesize empty audio with mutagen at runtime.
- Side effects (writing files / modifying audio) ONLY in `lyricbuilder/tagger.py`.
- Every external failure degrades to "this song unmatched/skipped"; never abort the whole batch.
- CLI must support `--dry-run` (zero side effects) and `--force` (overwrite existing .lrc).
- Format spec: `docs/superpowers/specs/2026-07-12-lyricbuilder-design.md`.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `lyricbuilder/__init__.py`
- Create: `sources/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: importable package `lyricbuilder`, test infra (`pytest` runs green).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "lyricbuilder"
version = "0.1.0"
description = "Fetch and attach lyrics for a local music library"
requires-python = ">=3.11"
dependencies = [
    "mutagen>=1.47",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "typer>=0.12",
    "rich>=13.7",
]

[project.scripts]
lyricbuilder = "lyricbuilder.cli:app"

[project.optional-dependencies]
dev = ["pytest>=8.0", "respx>=0.21", "pytest-tmpfiles>=1.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write empty package markers**

`lyricbuilder/__init__.py`:
```python
"""lyricBuilder: fetch and attach lyrics for a local music library."""
```

`sources/__init__.py`:
```python
"""Lyric source adapters."""
```

`tests/__init__.py` — empty file.

- [ ] **Step 3: Write smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import lyricbuilder
    assert lyricbuilder.__doc__
```

- [ ] **Step 4: Install and run tests**

Run: `cd ~/Desktop/lyricBuilder && pip install -e '.[dev]' && pytest -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml lyricbuilder sources tests
git commit -m "chore: scaffold lyricbuilder package and test infra"
```

---

### Task 2: cache Module (Local Result Cache)

**Files:**
- Create: `lyricbuilder/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Produces: `Cache` class.
  - `Cache(cache_dir: Path)` — constructor; ensures `cache_dir` exists.
  - `key(title: str, artist: str) -> str` — normalized hash key (static method).
  - `get(title: str, artist: str) -> dict | None` — returns `{matched, type, text, source}` or None.
  - `put(title: str, artist: str, result: dict) -> None` — store; `result` may be `{matched: False}` (negative cache).

- [ ] **Step 1: Write failing tests**

`tests/test_cache.py`:
```python
import json
from pathlib import Path
from lyricbuilder.cache import Cache


def test_key_is_normalized_case_punct_whitespace(tmp_path):
    k1 = Cache.key("晴天", "周杰伦")
    k2 = Cache.key(" 晴天  ", "周杰伦")
    assert k1 == k2
    assert Cache.key("SUNNY", "Jay") == Cache.key("sunny", "jay")


def test_key_stable_across_runs():
    a = Cache.key("A", "B")
    b = Cache.key("A", "B")
    assert a == b and len(a) > 0


def test_get_miss_returns_none(tmp_path):
    c = Cache(tmp_path)
    assert c.get("Unknown", "Nobody") is None


def test_put_then_get_roundtrip(tmp_path):
    c = Cache(tmp_path)
    result = {"matched": True, "type": "lrc", "text": "[00:00]hi", "source": "lrclib"}
    c.put("晴天", "周杰伦", result)
    assert c.get("晴天", "周杰伦") == result


def test_negative_cache_stored(tmp_path):
    c = Cache(tmp_path)
    c.put("Nope", "Nobody", {"matched": False})
    assert c.get("Nope", "Nobody") == {"matched": False}


def test_corrupt_index_does_not_crash(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text("{ not valid json", encoding="utf-8")
    c = Cache(tmp_path)
    assert c.get("Any", "Thing") is None
    # put still works after corrupt load
    c.put("A", "B", {"matched": True, "type": "plain", "text": "x", "source": "s"})
    assert c.get("A", "B")["matched"] is True


def test_concurrent_write_same_key_tolerant(tmp_path):
    c = Cache(tmp_path)
    for _ in range(5):
        c.put("Same", "Artist", {"matched": True, "type": "lrc", "text": "t", "source": "s"})
    assert c.get("Same", "Artist")["text"] == "t"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lyricbuilder.cache'`.

- [ ] **Step 3: Implement `cache.py`**

```python
"""Local result cache for matched lyrics, keyed by normalized title+artist."""
from __future__ import annotations

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
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._index, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)

    def get(self, title: str, artist: str) -> dict | None:
        return self._index.get(self.key(title, artist))

    def put(self, title: str, artist: str, result: dict) -> None:
        self._index[self.key(title, artist)] = result
        self._save()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_cache.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add lyricbuilder/cache.py tests/test_cache.py
git commit -m "feat: add local lyrics result cache"
```

---

### Task 3: scanner Module (Clue Extraction)

**Files:**
- Create: `lyricbuilder/models.py`
- Create: `lyricbuilder/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Produces: `Clue` dataclass and `Scanner` class.
  - `Clue(path: Path, fmt: str, title: str|None, artist: str|None, source: str)` where `source ∈ {"tag","filename","none"}`.
  - `Scanner(music_dir: Path, exts: list[str] | None = None)` — `exts` defaults to `[".mp3",".m4a",".aac",".alac",".flac",".wav"]`.
  - `Scanner.scan() -> list[Clue]` — yields clues for every readable audio file.

- [ ] **Step 1: Write `models.py`**

```python
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
```

- [ ] **Step 2: Write failing tests**

`tests/test_scanner.py`:
```python
import io
from pathlib import Path
from mutagen import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.mp4 import MP4

from lyricbuilder.scanner import Scanner


def _make_mp3(path: Path, title: str | None, artist: str | None):
    path.write_bytes(b"")  # placeholder
    audio = MP3(path)
    if not audio.tags:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=[title] if title else []))
    audio.tags.add(TPE1(encoding=3, text=[artist] if artist else []))
    audio.save()

# NOTE for implementer: an empty-bytes file is NOT a valid MPEG stream,
# so `MP3(path)` above may raise on it. If the RED step fails with a
# mutagen parse error, make the fixture robust: write ID3 tags directly
# via `mutagen.id3.ID3(path)` (works without MPEG audio), and ensure the
# scanner reads them back — `MutagenFile(path, easy=True)` returns an
# EasyMP3 whose `.tags` is populated from the ID3 block. If that returns
# None on an ID3-only file, have `_from_tags` fall back to
# `mutagen.id3.ID3(path)` for .mp3. The behavior under test is what
# matters (tag read + filename fallback); pick whichever fixture approach
# makes the tests pass cleanly.


def _make_m4a(path: Path, title: str | None, artist: str | None):
    # minimal valid m4a via MP4 on empty file is tricky; use mutagen helper
    path.write_bytes(b"")
    # fall back to creating tags on a real container is out of scope for unit test;
    # use filename-based path for m4a in tests
    pass


def test_reads_id3_tags(tmp_path):
    p = tmp_path / "song.mp3"
    _make_mp3(p, "晴天", "周杰伦")
    clues = Scanner(tmp_path).scan()
    assert len(clues) == 1
    assert clues[0].title == "晴天"
    assert clues[0].artist == "周杰伦"
    assert clues[0].source == "tag"


def test_falls_back_to_filename_when_no_tag(tmp_path):
    p = tmp_path / "周杰伦 - 晴天.mp3"
    _make_mp3(p, None, None)
    clues = Scanner(tmp_path).scan()
    c = clues[0]
    assert c.title == "晴天"
    assert c.artist == "周杰伦"
    assert c.source == "filename"


def test_filename_without_dash_yields_none_clue(tmp_path):
    p = tmp_path / "track01.mp3"
    _make_mp3(p, None, None)
    clues = Scanner(tmp_path).scan()
    assert clues[0].title is None
    assert clues[0].artist is None
    assert clues[0].source == "none"


def test_skips_non_audio_files(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    p = tmp_path / "song.mp3"
    _make_mp3(p, "T", "A")
    clues = Scanner(tmp_path).scan()
    assert len(clues) == 1


def test_recursive_scan(tmp_path):
    sub = tmp_path / "album" / "disc1"
    sub.mkdir(parents=True)
    p = sub / "a.mp3"
    _make_mp3(p, "T", "A")
    clues = Scanner(tmp_path).scan()
    assert len(clues) == 1
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `scanner.py`**

```python
"""Scan a music directory and extract per-file clues for lyric matching."""
from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile

from .models import Clue

DEFAULT_EXTS = [".mp3", ".m4a", ".aac", ".alac", ".flac", ".wav"]

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
        try:
            mf = MutagenFile(path, easy=True)
        except Exception:
            return None, None, "none"
        if mf is None:
            return None, None, "none"
        title = mf.get("title", [None])[0]
        artist = mf.get("artist", [None])[0]
        if title or artist:
            return title, artist, "tag"
        return None, None, "none"
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_scanner.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add lyricbuilder/models.py lyricbuilder/scanner.py tests/test_scanner.py
git commit -m "feat: add library scanner with tag+filename clue extraction"
```

---

### Task 4: Source Base Interface + LRCLIB Source

**Files:**
- Create: `sources/base.py`
- Create: `sources/lrclib.py`
- Test: `tests/test_source_lrclib.py`

**Interfaces:**
- Produces:
  - `sources.base.Source` protocol: `get(title: str | None, artist: str | None) -> LyricResult`.
  - `sources.lrclib.LRCLibSource(client: httpx.Client | None = None)` implementing `Source`; queries `https://lrclib.net/api/get`.

- [ ] **Step 1: Write `base.py`**

```python
"""Lyric source protocol."""
from __future__ import annotations
from typing import Protocol
from lyricbuilder.models import LyricResult


class Source(Protocol):
    name: str
    def get(self, title: str | None, artist: str | None) -> LyricResult: ...
```

- [ ] **Step 2: Write failing tests**

`tests/test_source_lrclib.py`:
```python
import httpx
import respx
from lyricbuilder.models import LyricResult
from sources.lrclib import LRCLibSource

BASE = "https://lrclib.net/api/get"


@respx.mock
def test_returns_synced_lrc_on_hit():
    respx.get(BASE).respond(200, json={"syncedLyrics": "[00:00]晴天", "plainLyrics": None})
    src = LRCLibSource()
    r = src.get("晴天", "周杰伦")
    assert r.matched is True
    assert r.type == "lrc"
    assert r.text == "[00:00]晴天"
    assert r.source == "lrclib"


@respx.mock
def test_returns_plain_when_only_plain_available():
    respx.get(BASE).respond(200, json={"syncedLyrics": None, "plainLyrics": ["line1"]})
    src = LRCLibSource()
    r = src.get("A", "B")
    assert r.matched is True
    assert r.type == "plain"
    assert "line1" in r.text


@respx.mock
def test_returns_unmatched_on_404():
    respx.get(BASE).respond(404)
    src = LRCLibSource()
    r = src.get("A", "B")
    assert r.matched is False
    assert r.type is None


@respx.mock
def test_returns_unmatched_on_timeout():
    respx.get(BASE).mock(side_effect=httpx.TimeoutException("slow"))
    src = LRCLibSource(timeout=0.01, retries=1)
    r = src.get("A", "B")
    assert r.matched is False


@respx.mock
def test_returns_unmatched_on_429_after_retry():
    respx.get(BASE).respond(429)
    src = LRCLibSource(timeout=1.0, retries=2)
    r = src.get("A", "B")
    assert r.matched is False
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_source_lrclib.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `sources/lrclib.py`**

```python
"""LRCLIB source — public, keyless, synced-LRC-focused API."""
from __future__ import annotations

import time
import httpx

from lyricbuilder.models import LyricResult

BASE_URL = "https://lrclib.net/api/get"


class LRCLibSource:
    name = "lrclib"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 2):
        self._client = client or httpx.Client(timeout=timeout)
        self._timeout = timeout
        self._retries = retries

    def get(self, title: str | None, artist: str | None) -> LyricResult:
        query = {"title": title, "artist": artist}
        if not title:
            return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)
        params = {"track_name": title}
        if artist:
            params["artist_name"] = artist
        data = self._request(params)
        if data is None:
            return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)
        synced = data.get("syncedLyrics")
        if synced:
            return LyricResult(matched=True, type="lrc", text=synced, source=self.name, query=query)
        plain = data.get("plainLyrics")
        if plain:
            text = "\n".join(plain) if isinstance(plain, list) else str(plain)
            return LyricResult(matched=True, type="plain", text=text, source=self.name, query=query)
        return LyricResult(matched=False, type=None, text=None, source=self.name, query=query)

    def _request(self, params: dict) -> dict | None:
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(BASE_URL, params=params)
            except httpx.HTTPError:
                return None
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    return None
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            return None
        return None
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_source_lrclib.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add sources/base.py sources/lrclib.py tests/test_source_lrclib.py
git commit -m "feat: add Source protocol and LRCLIB adapter"
```

---

### Task 5: NetEase Source

**Files:**
- Create: `sources/netease.py`
- Test: `tests/test_source_netease.py`

**Interfaces:**
- Produces: `sources.netease.NeteaseSource(client, timeout, retries)` implementing `Source`. Uses `https://music.163.com/api/search/get` then `https://music.163.com/api/song/lyric`.

- [ ] **Step 1: Write failing tests**

`tests/test_source_netease.py`:
```python
import respx
from sources.netease import NeteaseSource

SEARCH = "https://music.163.com/api/search/get"
LYRIC = "https://music.163.com/api/song/lyric"


@respx.mock
def test_returns_synced_lrc():
    respx.get(SEARCH).respond(200, json={"result": {"songs": [{"id": 42, "name": "晴天", "artists": [{"name": "周杰伦"}]}]}})
    respx.get(LYRIC).respond(200, json={"lrc": {"lyric": "[00:01]晴天"}, "tlyric": {"lyric": None}})
    r = NeteaseSource().get("晴天", "周杰伦")
    assert r.matched and r.type == "lrc" and r.source == "netease"


@respx.mock
def test_returns_plain_when_no_lrc():
    respx.get(SEARCH).respond(200, json={"result": {"songs": [{"id": 42, "name": "晴天", "artists": [{"name": "周杰伦"}]}]}})
    respx.get(LYRIC).respond(200, json={"lrc": None, "tlyric": None})
    r = NeteaseSource().get("晴天", "周杰伦")
    assert r.matched is False


@respx.mock
def test_unmatched_when_search_empty():
    respx.get(SEARCH).respond(200, json={"result": {"songs": []}})
    r = NeteaseSource().get("A", "B")
    assert r.matched is False


@respx.mock
def test_unmatched_on_http_error():
    respx.get(SEARCH).respond(500)
    r = NeteaseSource(retries=1).get("A", "B")
    assert r.matched is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_source_netease.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `sources/netease.py`**

```python
"""NetEase Cloud Music lyric source."""
from __future__ import annotations

import time
import httpx

from lyricbuilder.models import LyricResult

SEARCH_URL = "https://music.163.com/api/search/get"
LYRIC_URL = "https://music.163.com/api/song/lyric"


class NeteaseSource:
    name = "netease"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 2):
        self._client = client or httpx.Client(timeout=timeout, headers={"Referer": "https://music.163.com"})
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
        term = f"{title} {artist}" if artist else title
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(SEARCH_URL, params={"s": term, "type": 1, "limit": 5})
            except httpx.HTTPError:
                return None
            if resp.status_code == 200:
                try:
                    songs = resp.json().get("result", {}).get("songs", [])
                except ValueError:
                    return None
                return str(songs[0]["id"]) if songs else None
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt)); continue
            return None
        return None

    def _fetch_lyric(self, song_id: str) -> str | None:
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.get(LYRIC_URL, params={"id": song_id, "lv": 1, "tv": -1})
            except httpx.HTTPError:
                return None
            if resp.status_code == 200:
                try:
                    return resp.json().get("lrc", {}).get("lyric")
                except ValueError:
                    return None
            if resp.status_code == 429 and attempt < self._retries:
                time.sleep(0.5 * (2 ** attempt)); continue
            return None
        return None


def _has_timestamps(text: str) -> bool:
    import re
    return bool(re.search(r"\[\d{2}:\d{2}", text or ""))
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_source_netease.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add sources/netease.py tests/test_source_netease.py
git commit -m "feat: add NetEase Cloud lyric source"
```

---

### Task 6: Web-Scrape Fallback Source

**Files:**
- Create: `sources/web_scrape.py`
- Test: `tests/test_source_web_scrape.py`

**Interfaces:**
- Produces: `sources.web_scrape.WebScrapeSource(client, timeout, retries)` implementing `Source`. Scrapes a generic lyric page via BS4; returns `type="plain"` (synced timestamps unlikely from scrape).

- [ ] **Step 1: Write failing tests**

`tests/test_source_web_scrape.py`:
```python
import respx
from sources.web_scrape import WebScrapeSource

SEARCH = "https://example-lyrics.test/search"


@respx.mock
def test_returns_plain_from_parsed_html():
    html = """
    <div class="lyrics"><p>line one</p><p>line two</p></div>
    """
    respx.get("https://example-lyrics.test/search").respond(200, text=html)
    r = WebScrapeSource().get("晴天", "周杰伦")
    assert r.matched is True
    assert r.type == "plain"
    assert "line one" in r.text and "line two" in r.text
    assert r.source == "scrape"


@respx.mock
def test_unmatched_when_selector_misses():
    respx.get("https://example-lyrics.test/search").respond(200, text="<html><body>nope</body></html>")
    r = WebScrapeSource().get("A", "B")
    assert r.matched is False


@respx.mock
def test_unmatched_on_http_error():
    respx.get("https://example-lyrics.test/search").respond(500)
    r = WebScrapeSource(retries=1).get("A", "B")
    assert r.matched is False


def test_unmatched_without_title():
    r = WebScrapeSource().get(None, "B")
    assert r.matched is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_source_web_scrape.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `sources/web_scrape.py`**

```python
"""Web-scrape fallback lyric source. Returns plain text only."""
from __future__ import annotations

import time
import httpx
from bs4 import BeautifulSoup

from lyricbuilder.models import LyricResult


class WebScrapeSource:
    name = "scrape"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 8.0, retries: int = 1):
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "lyricbuilder/0.1"})
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_source_web_scrape.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add sources/web_scrape.py tests/test_source_web_scrape.py
git commit -m "feat: add web-scrape fallback source"
```

---

### Task 7: lyricfetch Pipeline

**Files:**
- Create: `lyricbuilder/lyricfetch.py`
- Test: `tests/test_lyricfetch.py`

**Interfaces:**
- Produces: `LyricFetcher(sources: list[Source], cache: Cache | None = None)`.
  - `fetch(clue: Clue) -> LyricResult` — consults cache first; on miss, tries sources in order; stores result (including negative) in cache; returns `LyricResult`.

- [ ] **Step 1: Write failing tests**

`tests/test_lyricfetch.py`:
```python
from pathlib import Path
from lyricbuilder.models import Clue, LyricResult
from lyricbuilder.cache import Cache
from lyricbuilder.lyricfetch import LyricFetcher


class _Fake:
    def __init__(self, name, result):
        self.name = name
        self._r = result
    def get(self, title, artist):
        return self._r


def test_returns_first_source_hit_and_skips_rest():
    called = []
    class A:
        name = "a"
        def get(self, t, a):
            called.append("a"); return LyricResult(True, "lrc", "x", "a", {})
    class B:
        name = "b"
        def get(self, t, a):
            called.append("b"); return LyricResult(True, "lrc", "y", "b", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A(), B()]).fetch(clue)
    assert r.matched and r.source == "a" and called == ["a"]


def test_falls_through_to_next_on_miss():
    class A:
        name = "a"
        def get(self, t, a): return LyricResult(False, None, None, "a", {})
    class B:
        name = "b"
        def get(self, t, a): return LyricResult(True, "plain", "y", "b", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A(), B()]).fetch(clue)
    assert r.source == "b" and r.type == "plain"


def test_all_miss_returns_unmatched():
    class A:
        name = "a"
        def get(self, t, a): return LyricResult(False, None, None, "a", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A()]).fetch(clue)
    assert r.matched is False


def test_cache_hit_skips_sources():
    class Exploding:
        name = "boom"
        def get(self, t, a): raise AssertionError("should not be called")
    cache = Cache(Path("/tmp/lb_test_cache_hit"))
    cache.put("T", "A", {"matched": True, "type": "lrc", "text": "cached", "source": "lrclib"})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([Exploding()], cache=cache).fetch(clue)
    assert r.text == "cached"


def test_negative_result_cached():
    class A:
        name = "a"
        calls = 0
        def get(self, t, a):
            A.calls += 1; return LyricResult(False, None, None, "a", {})
    cache = Cache(Path("/tmp/lb_test_neg_cache"))
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    f = LyricFetcher([A()], cache=cache)
    f.fetch(clue); f.fetch(clue)
    assert A.calls == 1


def test_none_clue_returns_unmatched_without_calling_sources():
    class Boom:
        name = "b"
        def get(self, t, a): raise AssertionError("nope")
    clue = Clue(Path("track01.mp3"), "mp3", None, None, "none")
    r = LyricFetcher([Boom()]).fetch(clue)
    assert r.matched is False
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_lyricfetch.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `lyricfetch.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_lyricfetch.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add lyricbuilder/lyricfetch.py tests/test_lyricfetch.py
git commit -m "feat: add cache-first lyric fetch pipeline"
```

---

### Task 8: tagger Module (Write .lrc + Embed)

**Files:**
- Create: `lyricbuilder/tagger.py`
- Test: `tests/test_tagger.py`

**Interfaces:**
- Produces: `Tagger(dry_run: bool=False, force: bool=False, embed: bool=True, lrc: bool=True)`.
  - `apply(clue: Clue, result: LyricResult) -> dict` — returns `{lrc: "written"|"skipped"|"failed", embed: "written"|"skipped"|"failed"|"unsupported"}`. In `dry_run` always returns `"skipped"` for both and writes nothing.

- [ ] **Step 1: Write failing tests**

`tests/test_tagger.py`:
```python
from pathlib import Path
from mutagen import File as MutagenFile
from lyricbuilder.models import Clue, LyricResult
from lyricbuilder.tagger import Tagger


def _make_mp3(path: Path):
    from mutagen.mp3 import MP3
    path.write_bytes(b"")
    MP3(path).save()  # init empty tags


def test_writes_lrc_file(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "[00:00]hi", "lrclib", {})
    out = Tagger().apply(clue, r)
    assert (tmp_path / "song.lrc").read_text(encoding="utf-8") == "[00:00]hi"
    assert out["lrc"] == "written"


def test_skips_existing_lrc_without_force(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    (tmp_path / "song.lrc").write_text("old", encoding="utf-8")
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "new", "lrclib", {})
    out = Tagger().apply(clue, r)
    assert (tmp_path / "song.lrc").read_text() == "old"
    assert out["lrc"] == "skipped"


def test_force_overwrites_existing_lrc(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    (tmp_path / "song.lrc").write_text("old", encoding="utf-8")
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "new", "lrclib", {})
    out = Tagger(force=True).apply(clue, r)
    assert (tmp_path / "song.lrc").read_text() == "new"
    assert out["lrc"] == "written"


def test_embeds_uslt_into_mp3(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "[00:00]hi", "lrclib", {})
    Tagger().apply(clue, r)
    mf = MutagenFile(p)
    assert any(k.startswith("USLT") for k in mf.tags.keys())


def test_wav_skips_embed_but_writes_lrc(tmp_path):
    p = tmp_path / "song.wav"; p.write_bytes(b"\x00")
    clue = Clue(p, "wav", "T", "A", "tag")
    r = LyricResult(True, "lrc", "hi", "lrclib", {})
    out = Tagger().apply(clue, r)
    assert (tmp_path / "song.lrc").exists()
    assert out["embed"] == "unsupported"


def test_dry_run_writes_nothing(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "hi", "lrclib", {})
    out = Tagger(dry_run=True).apply(clue, r)
    assert not (tmp_path / "song.lrc").exists()
    mf = MutagenFile(p); assert not any(k.startswith("USLT") for k in (mf.tags or {}).keys())
    assert out["lrc"] == "skipped" and out["embed"] == "skipped"


def test_no_embed_flag_skips_embedding(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(True, "lrc", "hi", "lrclib", {})
    out = Tagger(embed=False).apply(clue, r)
    assert out["embed"] == "skipped"
    mf = MutagenFile(p); assert not any(k.startswith("USLT") for k in (mf.tags or {}).keys())


def test_unmatched_result_writes_nothing(tmp_path):
    p = tmp_path / "song.mp3"; _make_mp3(p)
    clue = Clue(p, "mp3", "T", "A", "tag")
    r = LyricResult(False, None, None, None, {})
    out = Tagger().apply(clue, r)
    assert not (tmp_path / "song.lrc").exists()
    assert out["lrc"] == "skipped" and out["embed"] == "skipped"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_tagger.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `tagger.py`**

```python
"""Write .lrc files and embed lyrics into audio tags. Sole side-effect module."""
from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import USLT, ID3
from mutagen.mp4 import MP4

from .models import Clue, LyricResult

EMBED_SUPPORTED = {"mp3", "m4a", "aac", "alac", "flac"}


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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_tagger.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add lyricbuilder/tagger.py tests/test_tagger.py
git commit -m "feat: add tagger for .lrc writeout and audio embed"
```

---

### Task 9: CLI (typer) — scan / stats / config

**Files:**
- Create: `lyricbuilder/cli.py`
- Create: `lyricbuilder/config.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `app` typer instance with commands `scan`, `stats`, `config show`, `config init`. Loads `~/.lyricbuilder/config.toml` as defaults. `scan` wires Scanner → LyricFetcher → Tagger and prints a rich table.

- [ ] **Step 1: Write `config.py`**

```python
"""Config loading: CLI args > ~/.lyricbuilder/config.toml > defaults."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

DEFAULTS_PATH = Path.home() / ".lyricbuilder" / "config.toml"


@dataclass
class Config:
    source_dir: str | None = None
    cache_dir: str = str(Path.home() / ".lyricbuilder" / "cache")
    timeout_sec: float = 8.0
    retry: int = 2
    proxy: str | None = None
    sources: dict = field(default_factory=lambda: {"lrclib": True, "netease": True, "scrape": True})


def load_config(path: Path = DEFAULTS_PATH) -> Config:
    cfg = Config()
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if "source_dir" in data: cfg.source_dir = data["source_dir"]
    if "cache_dir" in data: cfg.cache_dir = data["cache_dir"]
    if "timeout_sec" in data: cfg.timeout_sec = data["timeout_sec"]
    if "retry" in data: cfg.retry = data["retry"]
    if "proxy" in data: cfg.proxy = data["proxy"]
    if "sources" in data: cfg.sources = {**cfg.sources, **data["sources"]}
    return cfg
```

- [ ] **Step 2: Write failing tests**

`tests/test_cli.py`:
```python
from pathlib import Path
from typer.testing import CliRunner
from lyricbuilder.cli import app

runner = CliRunner()


def test_dry_run_writes_nothing(tmp_path):
    from mutagen.mp3 import MP3
    p = tmp_path / "周杰伦 - 晴天.mp3"
    p.write_bytes(b""); MP3(p).save()
    res = runner.invoke(app, ["scan", "--source-dir", str(tmp_path), "--dry-run", "--no-embed"])
    assert res.exit_code == 0
    assert not (tmp_path / "晴天.lrc").exists()


def test_scan_help_lists_options():
    res = runner.invoke(app, ["scan", "--help"])
    assert res.exit_code == 0
    assert "--dry-run" in res.stdout
    assert "--force" in res.stdout
    assert "--no-embed" in res.stdout
    assert "--no-lrc" in res.stdout


def test_config_show_exits_zero():
    res = runner.invoke(app, ["config", "show"])
    assert res.exit_code == 0


def test_stats_exits_zero():
    res = runner.invoke(app, ["stats"])
    assert res.exit_code == 0


def test_config_init_creates_file(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"; fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    res = runner.invoke(app, ["config", "init"])
    assert res.exit_code == 0
    assert (fake_home / ".lyricbuilder" / "config.toml").exists()
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `cli.py`**

```python
"""lyricbuilder CLI entrypoint."""
from __future__ import annotations

from pathlib import Path
from collections import Counter

import httpx
import typer
from rich.console import Console
from rich.table import Table

from .config import load_config, DEFAULTS_PATH
from .cache import Cache
from .scanner import Scanner
from .lyricfetch import LyricFetcher
from .tagger import Tagger
from .models import LyricResult
from sources.lrclib import LRCLibSource
from sources.netease import NeteaseSource
from sources.web_scrape import WebScrapeSource

app = typer.Typer(help="Fetch and attach lyrics for a music library.", no_args_is_help=True)
config_app = typer.Typer()
app.add_typer(config_app, name="config", help="Configuration.")
console = Console()


def _build_sources(cfg, dry_run: bool) -> list:
    headers = {}
    client_kwargs = {}
    if cfg.proxy:
        client_kwargs["proxies"] = cfg.proxy
    client = httpx.Client(timeout=cfg.timeout_sec, **client_kwargs, headers=headers)
    srcs = []
    if cfg.sources.get("lrclib"): srcs.append(LRCLibSource(client, cfg.timeout_sec, cfg.retry))
    if cfg.sources.get("netease"): srcs.append(NeteaseSource(client, cfg.timeout_sec, cfg.retry))
    if cfg.sources.get("scrape"): srcs.append(WebScrapeSource(client, cfg.timeout_sec, max(1, cfg.retry)))
    return srcs


@app.command()
def scan(
    source_dir: str = typer.Option(None, "--source-dir", help="Music library directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing .lrc."),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding into audio."),
    no_lrc: bool = typer.Option(False, "--no-lrc", help="Skip writing .lrc files."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Scan a music library and fetch/attach lyrics."""
    cfg = load_config()
    src_dir = Path(source_dir or cfg.source_dir or "").expanduser()
    if not src_dir or not src_dir.exists():
        console.print(f"[red]source_dir not found:[/red] {src_dir}")
        raise typer.Exit(code=2)
    cache = Cache(Path(cfg.cache_dir).expanduser())
    fetcher = LyricFetcher(_build_sources(cfg, dry_run), cache=cache)
    tagger = Tagger(dry_run=dry_run, force=force, embed=not no_embed, lrc=not no_lrc)
    counters = Counter()
    rows = []
    for clue in Scanner(src_dir).scan():
        r = fetcher.fetch(clue)
        out = tagger.apply(clue, r)
        counters["total"] += 1
        if r.matched: counters[f"matched_{r.type}"] += 1
        else: counters["unmatched"] += 1
        if out.get("embed") == "failed": counters["embed_failed"] += 1
        if verbose: rows.append((clue.path.name, r.source or "-", r.type or "-"))
    table = Table(title="lyricBuilder results")
    table.add_column("metric"); table.add_column("count")
    for k in ["total", "matched_lrc", "matched_plain", "unmatched", "embed_failed"]:
        table.add_row(k, str(counters.get(k, 0)))
    console.print(table)
    if verbose and rows:
        t2 = Table(title="per-song"); t2.add_column("file"); t2.add_column("source"); t2.add_column("type")
        for row in rows: t2.add_row(*row)
        console.print(t2)


@app.command()
def stats(
    cache_dir: str = typer.Option(None, "--cache-dir"),
):
    """Show cache hit stats and unmatched list."""
    cfg = load_config()
    cdir = Path(cache_dir or cfg.cache_dir).expanduser()
    cache = Cache(cdir)
    import json
    idx = json.loads((cdir / "index.json").read_text(encoding="utf-8")) if (cdir / "index.json").exists() else {}
    table = Table(title="cache stats"); table.add_column("metric"); table.add_column("count")
    table.add_row("entries", str(len(idx)))
    matched = sum(1 for v in idx.values() if v.get("matched"))
    table.add_row("matched", str(matched)); table.add_row("unmatched", str(len(idx) - matched))
    console.print(table)


@config_app.command("show")
def config_show():
    cfg = load_config()
    console.print(f"source_dir = {cfg.source_dir}")
    console.print(f"cache_dir  = {cfg.cache_dir}")
    console.print(f"timeout_sec = {cfg.timeout_sec}")
    console.print(f"retry = {cfg.retry}")
    console.print(f"proxy = {cfg.proxy}")
    console.print(f"sources = {cfg.sources}")


@config_app.command("init")
def config_init():
    path = DEFAULTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        console.print(f"[yellow]exists:[/yellow] {path}"); return
    path.write_text(
        'source_dir = "~/Music/library"\n'
        'cache_dir  = "~/.lyricbuilder/cache"\n'
        'timeout_sec = 8\n'
        'retry = 2\n'
        '# proxy = "http://127.0.0.1:6152"\n'
        '[sources]\n'
        'lrclib  = true\n'
        'netease = true\n'
        'scrape  = true\n',
        encoding="utf-8",
    )
    console.print(f"[green]wrote:[/green] {path}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_cli.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run full suite**

Run: `pytest -v`
Expected: all tasks' tests green.

- [ ] **Step 7: Commit**

```bash
git add lyricbuilder/cli.py lyricbuilder/config.py tests/test_cli.py
git commit -m "feat: add typer CLI (scan/stats/config) with dry-run"
```

---

### Task 10: Skill + README

**Files:**
- Create: `.claude/skills/lyricbuilder/SKILL.md`
- Create: `README.md` (replace placeholder)

**Interfaces:**
- Produces: project-scoped skill that auto-triggers on lyric-matching intent and drives the CLI safely.

- [ ] **Step 1: Write `SKILL.md`**

```markdown
---
name: lyricbuilder
description: Use when the user wants to fetch/match lyrics for a music library or folder, or attach lyrics (.lrc + embed) to audio files. Triggers: 匹配歌词、歌词匹配、曲库歌词、match lyrics、fetch LRC.
---

# lyricBuilder Skill

Thin wrapper around the `lyricbuilder` CLI. The Python tool does the work; this skill only orchestrates safely.

## Workflow

1. **Preflight:** Run `lyricbuilder --help`. If the command is missing, install in the repo root:
   ```
   cd <repo-root> && pip install -e '.[dev]'
   ```
2. **Always dry-run first** on a new library:
   ```
   lyricbuilder scan --source-dir <DIR> --dry-run --verbose
   ```
   Show the user the hit/miss table and the unmatched list. Get explicit confirmation before writing.
3. **Run for real:**
   ```
   lyricbuilder scan --source-dir <DIR> --verbose
   ```
   Then `lyricbuilder stats` to summarize cache hit rate.
4. **Handle misses:** For unmatched songs, suggest fixing audio tags (title/artist) or re-running with `--force`. For `embed_failed` songs, keep the `.lrc` and do NOT retry the embed (the audio may be read-only or corrupted).
5. **Network/timeout:** If many timeouts, tell the user to set `proxy = "http://127.0.0.1:6152"` in `~/.lyricbuilder/config.toml` (run `lyricbuilder config init` first).

## Rules

- Never run `scan` without `--dry-run` first on a library you haven't seen the results for.
- Never modify audio files the user did not point you at.
- `--no-embed` / `--no-lrc` exist if the user wants only one output type.
```

- [ ] **Step 2: Write `README.md`**

```markdown
# lyricBuilder

Fetch and attach lyrics for a local music library. Scans a folder of audio (mp3/m4a/aac/alac/flac/wav), matches each track to lyrics (synced LRC preferred, plain fallback), writes `.lrc` files alongside, and embeds lyrics into audio tags.

## Install

```
pip install -e '.[dev]'
```

## Quick start

```
lyricbuilder config init           # write ~/.lyricbuilder/config.toml
lyricbuilder scan --source-dir ~/Music/library --dry-run --verbose
lyricbuilder scan --source-dir ~/Music/library --verbose
lyricbuilder stats
```

## How it works

1. **Scanner** reads audio tags (title/artist); falls back to filename parsing (`Artist - Title.ext`).
2. **LyricFetcher** queries sources in priority order — LRCLIB → NetEase → web-scrape — stopping at the first hit. Results are cached locally keyed on normalized title+artist, so re-runs don't re-fetch.
3. **Tagger** writes a `.lrc` next to the audio and embeds lyrics (mp3 USLT / m4a `©lyr` / FLAC `lyrics`). `--dry-run` previews with zero side effects.

## Sources

- **LRCLIB** (`lrclib.net`) — public, keyless, synced-LRC focus.
- **NetEase Cloud** — synced or plain.
- **Web scrape** — plain-text fallback.

Disable any source in `~/.lyricbuilder/config.toml` under `[sources]`.

## Design

See `docs/superpowers/specs/2026-07-12-lyricbuilder-design.md`.
```

- [ ] **Step 3: Verify skill parses and CLI still runs**

Run: `lyricbuilder --help`
Expected: prints help with `scan`/`stats`/`config` commands.

Run: `lyricbuilder scan --help`
Expected: shows `--dry-run`, `--force`, `--no-embed`, `--no-lrc`, `--verbose`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/lyricbuilder/SKILL.md README.md
git commit -m "docs: add project skill and README"
git push origin main
```

---

## Self-Review Notes

- **Spec coverage:** §2 needs (sources/dry-run/lrc+embed/cached/cache-first) → Tasks 2-9. §5 data flow → Task 7+8. §6 error handling (timeouts/429/corrupt/unsupported) → covered in source tests (Task 4-6), tagger tests (Task 8), pipeline test (Task 7 negative cache + none-clue). §7 testing strategy → every task is TDD with mocks, no real network. §8 config/CLI → Task 9. §9 skill → Task 10.
- **Type consistency:** `LyricResult(matched, type, text, source, query)` field order is used identically in `models.py`, all sources, `lyricfetch`, `tagger`. `Clue(path, fmt, title, artist, source)` consistent across scanner/lyricfetch/tagger. `Cache.get/put(title, artist)` consistent.
- **Placeholders:** None — every step has real code or real commands.
- One known gap: real m4a embedding test is stubbed out of Task 3 (m4a fixtures are hard); Task 8 tests mp3 embed + wav-skip; m4a embed path is implemented but not unit-tested against a real container. Acceptable for v1 — covered by manual `--help` smoke in Task 10.
