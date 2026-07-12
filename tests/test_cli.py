from pathlib import Path
from typer.testing import CliRunner
from lyricbuilder.cli import app
from lyricbuilder.config import Config

import respx
from mutagen.id3 import ID3

runner = CliRunner()

# Two valid MPEG-1 Layer III frames (128kbps/44.1kHz, 417 bytes each).
_MP3_FRAMES = (bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413) * 2

LRCLIB_URL = "https://lrclib.net/api/get"
_LRC_TEXT = "[00:00]Some Title\n[00:05]line two"


def _make_mp3(tmp_path: Path) -> Path:
    """Clue-bearing fixture: filename parses to title='Some Title', artist='Some Artist'."""
    p = tmp_path / "Some Artist - Some Title.mp3"
    p.write_bytes(_MP3_FRAMES)
    ID3().save(p)
    return p


def _hermetic_config(tmp_path: Path) -> Config:
    return Config(
        source_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        sources={"lrclib": True, "netease": False, "scrape": False},
    )


@respx.mock
def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    _make_mp3(tmp_path)
    monkeypatch.setattr("lyricbuilder.cli.load_config", lambda *a, **kw: _hermetic_config(tmp_path))
    respx.get(LRCLIB_URL).respond(200, json={"syncedLyrics": _LRC_TEXT, "plainLyrics": None})
    res = runner.invoke(app, ["scan", "--source-dir", str(tmp_path), "--dry-run", "--no-embed"])
    assert res.exit_code == 0
    # dry-run must be zero side effects: no .lrc, no cache dir/index.json.
    assert not (tmp_path / "Some Artist - Some Title.lrc").exists()
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "cache" / "index.json").exists()


@respx.mock
def test_default_run_writes_lrc(tmp_path, monkeypatch):
    _make_mp3(tmp_path)
    monkeypatch.setattr("lyricbuilder.cli.load_config", lambda *a, **kw: _hermetic_config(tmp_path))
    respx.get(LRCLIB_URL).respond(200, json={"syncedLyrics": _LRC_TEXT, "plainLyrics": None})
    res = runner.invoke(app, ["scan", "--source-dir", str(tmp_path), "--no-embed"])
    assert res.exit_code == 0
    # without --dry-run the .lrc IS written (proves the test exercises the feature).
    lrc = tmp_path / "Some Artist - Some Title.lrc"
    assert lrc.exists()
    assert _LRC_TEXT in lrc.read_text(encoding="utf-8")


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
