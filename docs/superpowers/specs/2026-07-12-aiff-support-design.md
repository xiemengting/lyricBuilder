# AIFF Support — Design Spec

**Date:** 2026-07-12
**Status:** Approved (pre-implementation)
**Scope:** Add full `.aiff` support to lyricBuilder — scan, ID3-tag clue extraction, and USLT lyric embedding.

## Motivation

lyricBuilder's scanner only recognizes `[".mp3", ".m4a", ".aac", ".alac", ".flac", ".wav"]` and its tagger only embeds lyrics into `{"mp3", "m4a", "aac", "alac", "flac"}`. A real user library of 8 AIFF tracks (`腰樂隊 - 腰樂隊 24'相見恨晚`) scans to **0 files** and cannot be embedded. AIFF is a common lossless format (Apple Music / Audio Hijack exports); the tool should handle it.

## Verified facts (grounding)

Probed a real AIFF from the target directory with `mutagen.aiff` (mutagen 1.48.1):

1. **`mutagen.aiff.AIFF` loads AIFF and exposes an `_IFFID3` tags object** (an ID3 subclass). The file already carries `TIT2` (title), `TPE1` (artist), `TALB` (album), `TRCK`, `APIC` — i.e. well-tagged.
2. **`MutagenFile(path, easy=True)` does NOT surface easy keys for AIFF** — it returns the raw AIFF object with frame keys `{'TIT2': ..., 'TPE1': ...}`, so `mf.get("title"/"artist")` returns `None`. The scanner's current easy path therefore cannot read AIFF tags and falls back to filename parsing, which mangles `ARTIST - ALBUM - NN TRACK` three-segment names (the existing `_parse_filename` splits only once). **Tag-based clue extraction for AIFF requires a new code path.**
3. **USLT embed + readback round-trips correctly** via `AIFF(path).tags.setall("USLT", [USLT(encoding=3, lang="chi", desc="", text=text)]); a.save()`. Readback via a fresh `AIFF(path)` returns the exact text.
4. **Bare `ID3(path)` raises `ID3NoHeaderError` on AIFF** — AIFF stores ID3 in an `ID3 ` chunk that `mutagen.aiff.AIFF` knows how to locate, but the standalone `ID3()` loader does not. **The tagger must use `mutagen.aiff.AIFF`, never the mp3-style `ID3()` direct load.**

## Design

### 1. `lyricbuilder/scanner.py`

- `DEFAULT_EXTS`: append `".aiff"` → `[".mp3", ".m4a", ".aac", ".alac", ".flac", ".wav", ".aiff"]`.
- `_from_tags`: extend the existing ID3-fallback block. Currently the fallback only runs `if path.suffix.lower() == ".mp3"`. Add a parallel `.aiff` branch:
  - Load `from mutagen.aiff import AIFF; a = AIFF(path)` (guard with `try/except` → return `None, None, "none"` on failure, matching the mp3 fallback's contract).
  - Read `tags = a.tags`; if `tags is None`, fall through to filename.
  - `tit2 = tags.getall("TIT2")`, `tpe1 = tags.getall("TPE1")`; pull `tit2[0].text[0]` / `tpe1[0].text[0]` with the same truthiness guards as the mp3 branch.
  - Return `(title, artist, "tag")` if either is present, else fall through to filename.
- Keep the mp3 branch unchanged. The two branches are independent because `ID3(path)` works for mp3 but raises for AIFF.

### 2. `lyricbuilder/tagger.py`

- `EMBED_SUPPORTED`: add `"aiff"` → `{"mp3", "m4a", "aac", "alac", "flac", "aiff"}`.
- `_embed` dispatch: add `if clue.fmt == "aiff": return self._embed_aiff(clue.path, text)` (before the trailing `return "failed"`).
- New `_embed_aiff(path, text) -> str` static method:
  - `from mutagen.aiff import AIFF` (top-level import alongside existing `from mutagen.id3 import USLT, ID3`).
  - `a = AIFF(path)`.
  - `if a.tags is None: a.add_tags()`.
  - `a.tags.setall("USLT", [USLT(encoding=3, lang="chi", desc="", text=text)])`.
  - `a.save()`.
  - `return "written"`.
  - Wrap in the existing `try/except Exception: return "failed"` from the `_embed` caller (no per-method try needed — matches `_embed_mp4`/`_embed_flac` shape).

### 3. Tests

**Fixture `_make_aiff(path, *, title=None, artist=None)`** — a local helper defined in each test file that needs it (mirroring the existing `_make_mp3`, which today is duplicated in `tests/test_scanner.py:9` and `tests/test_tagger.py:14` with no shared `conftest.py`). Philosophy matches the Task 8 `_make_mp3`:
- `import aifc, struct`; `with aifc.open(path, "w") as w: w.aiff(); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframesraw(b"\x00\x00")` — produces a minimal valid AIFF container with audio data.
- Then `from mutagen.aiff import AIFF; a = AIFF(path); a.add_tags()` (or rely on `a.tags`), and attach `TIT2`/`TPE1` via `a.tags.setall("TIT2", [TIT2(encoding=3, text=[title])])` etc. when provided; `a.save()`.
- No external sample committed, no user audio touched.

**`tests/test_scanner.py`** — new cases:
- `test_aiff_reads_tags`: AIFF with TIT2=`情書`, TPE1=`腰樂隊` → `Clue.source == "tag"`, `title == "情書"`, `artist == "腰樂隊"`, `fmt == "aiff"`.
- `test_aiff_without_tags_falls_back_to_filename`: AIFF with no tags, filename stem `Artist - Title` → `source == "filename"`, expected title/artist. (Confirms the no-tag path still works for AIFF, not just mp3.)
- `test_aiff_in_default_exts`: `".aiff" in Scanner.DEFAULT_EXTS` (cheap guard against regression).

**`tests/test_tagger.py`** — new cases:
- `test_embed_aiff_writes_uslt`: build fixture AIFF (no tags), run `Tagger()._embed_aiff(path, "[00:01.00]line\n[00:03.00]two")` (or via `Tagger.apply` with `embed=True, lrc=False`), then `AIFF(path).tags.getall("USLT")[0].text` matches the input.
- `test_aiff_in_embed_supported`: `"aiff" in EMBED_SUPPORTED`.
- `test_embed_aiff_unsupported_fmt_unchanged`: existing behavior — a fmt not in `EMBED_SUPPORTED` returns `"unsupported"`; ensure adding `aiff` didn't disturb the dispatch (covered by re-running the full existing suite).

### Data flow (unchanged shape)

`Scanner.scan()` yields `Clue(path, fmt="aiff", title, artist, source)` → `LyricFetcher` queries sources (LRCLIB / NetEase / web-scrape, unchanged) → `Tagger.apply(clue, result)` dispatches to `_embed_aiff` + writes `.lrc`. The only new surface is the AIFF branches in scanner/tagger; no fetcher, cache, source, or CLI change.

## Error handling

- Scanner: AIFF load failures are swallowed into the `none` source and fall through to filename, then to a `Clue` with `source="none"` — same as mp3 today. Never raises.
- Tagger: `_embed_aiff` exceptions are caught by `_embed`'s `try/except` → returns `"failed"`. The `embed_failed` stat increments and the `.lrc` is still written (per existing `apply` contract). User keeps the `.lrc` and does not retry embed, per the skill's miss-handling rule.

## Non-goals

- `.aif` / `.aifc` (AIFC compressed) support — only `.aiff`. YAGNI; revisit if a real library needs them.
- Refactoring the easy-mode tag reading into a unified ID3 path — touches mp3 (regression risk), out of scope.
- New lyric sources, CLI changes, cache changes — none needed.

## Risk

Low. New ext list entry + new scanner branch + new tagger method; existing mp3/m4a/flac code paths untouched. The only fiddly part is the `aifc`-based fixture, which uses only the stdlib and is fully under test control. Round-trip embed/readback already verified on a real AIFF (see Verified facts #3).
