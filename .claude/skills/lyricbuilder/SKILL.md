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
