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
    client = httpx.Client(timeout=cfg.timeout_sec, trust_env=False, **client_kwargs, headers=headers)
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
    cache = None if dry_run else Cache(Path(cfg.cache_dir).expanduser())
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
    path = Path.home() / ".lyricbuilder" / "config.toml"
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
