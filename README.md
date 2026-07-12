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
