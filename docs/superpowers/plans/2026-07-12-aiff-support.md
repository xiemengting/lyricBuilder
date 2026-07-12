# AIFF Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make lyricBuilder scan `.aiff` files, extract title/artist from their ID3 tags, and embed USLT lyrics — full parity with mp3/m4a/flac.

**Architecture:** Two independent, surgical additions following existing dispatch patterns. Scanner gains `.aiff` in `DEFAULT_EXTS` and a new `.aiff` branch in `_from_tags` that reads `TIT2`/`TPE1` ID3 frames via `mutagen.aiff.AIFF` (because `MutagenFile(easy=True)` does not surface easy keys for AIFF). Tagger gains `aiff` in `EMBED_SUPPORTED`, a dispatch arm, and `_embed_aiff` using `AIFF(path).tags.setall("USLT", ...)` (bare `ID3(path)` raises `ID3NoHeaderError` on AIFF — verified). No fetcher/cache/source/CLI changes.

**Tech Stack:** Python ≥3.11, mutagen (aiff module), stdlib `aifc` for test fixtures, pytest. Run tests via `.venv/bin/pytest` (project venv, Python 3.11.15) — do NOT use the anaconda base `pip`/`pytest` (Python 3.10.9 < requires-python).

## Global Constraints

- Requires-python `>=3.11` (per `pyproject.toml`). Use `.venv/bin/python` and `.venv/bin/pytest` only.
- Spec §八 (proxy): httpx clients use `trust_env=False` — NOT relevant here (no httpx touched), but do not introduce any `trust_env=True`/env-proxy code.
- Spec §三: scanner must never raise — AIFF load failures swallow into `source="none"`. Tag reading falls through to filename, then `none`.
- Tagger `apply` contract: embed failure → `"failed"` stat, `.lrc` still written (caller keeps `.lrc`, does not retry embed).
- Memory `brief-code-known-bugs`: briefs ship buggy example code; **the tests in this plan are the contract** — every fixture/snippet below has been verified against the real `.venv` interpreter.
- Test fixtures: mirror the existing `_make_mp3` philosophy (local helper per test file, no shared `conftest.py`). `_make_mp3` currently lives in BOTH `tests/test_scanner.py:9` and `tests/test_tagger.py:14`.
- Commits: one per task, on branch `feat/aiff-support` (already checked out). End commit messages with `Co-Authored-By: Claude <noreply@anthropic.com>`.

## File Structure

- **Modify** `lyricbuilder/scanner.py` — `DEFAULT_EXTS` list (line 12) + `_from_tags` method (lines 47-75): add `.aiff` ext + an `elif` AIFF branch reading ID3 frames via `mutagen.aiff.AIFF`.
- **Modify** `lyricbuilder/tagger.py` — `EMBED_SUPPORTED` set (line 12) + `_embed` dispatch (lines 44-58) + new `_embed_aiff` static method: add AIFF embed path.
- **Modify** `tests/test_scanner.py` — add `_make_aiff` helper + 3 tests.
- **Modify** `tests/test_tagger.py` — add `_make_aiff` helper + 2 tests.

No new files. No changes to `models.py`, `lyricfetch.py`, `sources/*`, `cli.py`, `cache.py`.

---

### Task 1: Scanner reads AIFF ID3 tags

**Files:**
- Modify: `lyricbuilder/scanner.py:12` (`DEFAULT_EXTS`) and `lyricbuilder/scanner.py:47-75` (`_from_tags`)
- Test: `tests/test_scanner.py` (append helper + tests)

**Interfaces:**
- Consumes: `mutagen.aiff.AIFF` (std lib mutagen, already installed).
- Produces: `Scanner.scan()` now yields `Clue(path=..., fmt="aiff", title=..., artist=..., source="tag"|"filename"|"none")` for `.aiff` files. `DEFAULT_EXTS` includes `".aiff"`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_scanner.py`)**

Add `aifc` + `warnings` imports at top of file (after existing imports), and the `_make_aiff` helper + tests. The full block to **append** to `tests/test_scanner.py`:

```python
import warnings  # add to existing imports at top
import aifc       # add to existing imports at top
from mutagen.aiff import AIFF  # add to existing imports at top
from mutagen.id3 import TIT2, TPE1  # TIT2/TPE1 already? no — only ID3 is imported at line 3; add TIT2, TPE1


def _make_aiff(path: Path, title: str | None, artist: str | None):
    # aifc writes a valid AIFF container with real audio data; mutagen.aiff
    # then loads it and we attach ID3 frames. (aifc is deprecated in 3.11
    # but present; suppress the import-time warning.)
    with open(path, "wb") as fh:
        with aifc.open(fh, "w") as w:
            w.aiff(); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
            w.writeframesraw(b"\x00\x00")
    a = AIFF(path)
    if a.tags is None:
        a.add_tags()
    if title:
        a.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        a.tags.add(TPE1(encoding=3, text=[artist]))
    a.save()


def test_aiff_reads_id3_tags(tmp_path):
    p = tmp_path / "track.aiff"
    _make_aiff(p, "情書", "腰樂隊")
    clues = Scanner(tmp_path).scan()
    assert len(clues) == 1
    assert clues[0].fmt == "aiff"
    assert clues[0].title == "情書"
    assert clues[0].artist == "腰樂隊"
    assert clues[0].source == "tag"


def test_aiff_falls_back_to_filename_when_no_tag(tmp_path):
    p = tmp_path / "腰樂隊 - 情書.aiff"
    _make_aiff(p, None, None)
    clues = Scanner(tmp_path).scan()
    c = clues[0]
    assert c.fmt == "aiff"
    assert c.title == "情書"
    assert c.artist == "腰樂隊"
    assert c.source == "filename"


def test_aiff_in_default_exts():
    from lyricbuilder.scanner import DEFAULT_EXTS
    assert ".aiff" in DEFAULT_EXTS
```

Also add at the very top of the file (after the module docstring/imports), to silence the `aifc` deprecation noise across the whole test module:

```python
warnings.filterwarnings("ignore", category=DeprecationWarning, message="'aifc' is deprecated")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_scanner.py::test_aiff_reads_id3_tags tests/test_scanner.py::test_aiff_falls_back_to_filename_when_no_tag tests/test_scanner.py::test_aiff_in_default_exts -v`
Expected: FAIL — `test_aiff_in_default_exts` fails (`".aiff" not in DEFAULT_EXTS`); the two tag tests fail because `.aiff` is skipped during scan (0 clues) or the AIFF branch doesn't exist.

- [ ] **Step 3: Implement — update `lyricbuilder/scanner.py`**

3a. Line 12, change `DEFAULT_EXTS`:

```python
DEFAULT_EXTS = [".mp3", ".m4a", ".aac", ".alac", ".flac", ".wav", ".aiff"]
```

3b. In `_from_tags`, add an `elif` AIFF branch mirroring the existing `.mp3` branch. The method becomes (showing the block from the `.mp3` check onward):

```python
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
```

Leave everything above the `.mp3` check unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_scanner.py -v`
Expected: PASS — all existing mp3 tests + the 3 new AIFF tests green. Confirm no existing test regressed.

- [ ] **Step 5: Run the full suite to confirm no cross-module regression**

Run: `.venv/bin/pytest -q`
Expected: all green (was 47 passing before this task; now 47 + 3 = 50).

- [ ] **Step 6: Commit**

```bash
git add lyricbuilder/scanner.py tests/test_scanner.py
git commit -m "feat(scanner): read ID3 tags from .aiff files

Add .aiff to DEFAULT_EXTS and an _from_tags branch that reads
TIT2/TPE1 via mutagen.aiff.AIFF (easy-mode does not surface AIFF
tags). Falls through to filename then 'none', never raises."
```

(Append `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.)

---

### Task 2: Tagger embeds USLT lyrics into AIFF

**Files:**
- Modify: `lyricbuilder/tagger.py:6-8` (imports), `:12` (`EMBED_SUPPORTED`), `:44-58` (`_embed`), append `_embed_aiff`
- Test: `tests/test_tagger.py` (append helper + tests)

**Interfaces:**
- Consumes: `mutagen.aiff.AIFF`, `mutagen.id3.USLT` (already imported).
- Produces: `Tagger.apply(clue, result)` where `clue.fmt == "aiff"` embeds `USLT(encoding=3, lang="chi", desc="", text=text)` into the AIFF ID3 chunk and returns `embed="written"` (or `"failed"` on exception, caught by `_embed`).

- [ ] **Step 1: Write the failing tests (append to `tests/test_tagger.py`)**

Add imports + helper + tests. Append to `tests/test_tagger.py`:

```python
import warnings  # add to existing imports at top
import aifc       # add to existing imports at top
from mutagen.aiff import AIFF  # add to existing imports at top
from mutagen.id3 import TIT2, TPE1  # only USLT, ID3 imported at line 5; add TIT2, TPE1


def _make_aiff(path: Path):
    # Valid AIFF container via stdlib aifc + empty ID3 block (mirror of _make_mp3).
    with open(path, "wb") as fh:
        with aifc.open(fh, "w") as w:
            w.aiff(); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
            w.writeframesraw(b"\x00\x00")
    AIFF(path).save()  # ensure an ID3 chunk exists for embedding
```

And at the top of the file (after imports), add:

```python
warnings.filterwarnings("ignore", category=DeprecationWarning, message="'aifc' is deprecated")
```

Tests:

```python
def test_embeds_uslt_into_aiff(tmp_path):
    p = tmp_path / "song.aiff"; _make_aiff(p)
    clue = Clue(p, "aiff", "T", "A", "tag")
    r = LyricResult(True, "lrc", "[00:01.00]line\n[00:03.00]two", "lrclib", {})
    out = Tagger().apply(clue, r)
    assert out["embed"] == "written"
    uslt = AIFF(p).tags.getall("USLT")
    assert uslt and uslt[0].text == "[00:01.00]line\n[00:03.00]two"


def test_aiff_in_embed_supported():
    from lyricbuilder.tagger import EMBED_SUPPORTED
    assert "aiff" in EMBED_SUPPORTED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_tagger.py::test_embeds_uslt_into_aiff tests/test_tagger.py::test_aiff_in_embed_supported -v`
Expected: FAIL — `"aiff" not in EMBED_SUPPORTED`; `apply` returns `embed="unsupported"` (USLT not written).

- [ ] **Step 3: Implement — update `lyricbuilder/tagger.py`**

3a. Imports (line 5-8): add `USLT` already imported; add `from mutagen.aiff import AIFF`. The import block becomes:

```python
from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.id3 import USLT, ID3
from mutagen.mp4 import MP4
```

3b. `EMBED_SUPPORTED` (line 12):

```python
EMBED_SUPPORTED = {"mp3", "m4a", "aac", "alac", "flac", "aiff"}
```

3c. `_embed` dispatch — add the AIFF arm. The method becomes (showing from the `try:` onward):

```python
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
```

3d. Add `_embed_aiff` static method (append after `_embed_flac`):

```python
    @staticmethod
    def _embed_aiff(path: Path, text: str) -> str:
        a = AIFF(path)
        if a.tags is None:
            a.add_tags()
        a.tags.setall("USLT", [USLT(encoding=3, lang="chi", desc="", text=text)])
        a.save()
        return "written"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_tagger.py -v`
Expected: PASS — all existing mp3/m4a/flac/wav tests + 2 new AIFF tests green.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all green (50 from Task 1 + 2 = 52).

- [ ] **Step 6: Commit**

```bash
git add lyricbuilder/tagger.py tests/test_tagger.py
git commit -m "feat(tagger): embed USLT lyrics into .aiff

Add 'aiff' to EMBED_SUPPORTED and _embed_aiff using
mutagen.aiff.AIFF (bare ID3() raises ID3NoHeaderError on AIFF).
Mirrors _embed_mp3 USLT shape; failure path returns 'failed'."
```

(Append `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.)

---

## Verification (post-implementation, manual smoke)

After both tasks land, run against the real user library (dry-run first per the lyricbuilder skill):

```bash
.venv/bin/lyricbuilder scan --source-dir "/Users/tsemengting/Downloads/腰樂隊 - 腰樂隊 24'相見恨晚" --dry-run --verbose
```

Expected: `total = 8`, clues sourced from `"tag"` (TIT2/TPE1 present in the real files). Then, with user consent, a real run writes `.lrc` files and embeds USLT.

## Self-Review (run before handing off)

- **Spec coverage:** spec §1 (scanner `DEFAULT_EXTS` + `_from_tags` AIFF branch) → Task 1. spec §2 (tagger `EMBED_SUPPORTED` + dispatch + `_embed_aiff`) → Task 2. spec §3 (tests + `_make_aiff` fixture via `aifc`) → both tasks. Non-goals respected (no `.aif`/`.aifc`, no easy-mode refactor). ✓
- **Placeholder scan:** no TBD/TODO; every code step shows verifiable code; fixture + snippets pre-run against the real `.venv`. ✓
- **Type consistency:** `_make_aiff` signature: scanner variant `(path, title, artist)`, tagger variant `(path)` — matches the existing `_make_mp3` split (`test_scanner.py:_make_mp3(path,title,artist)` vs `test_tagger.py:_make_mp3(path)`). `_embed_aiff(path, text) -> str` matches `_embed_mp3`/`_embed_flac` shape. ✓
