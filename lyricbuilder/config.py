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
