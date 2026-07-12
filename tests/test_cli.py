from pathlib import Path
from typer.testing import CliRunner
from lyricbuilder.cli import app
from lyricbuilder.config import Config

from mutagen.id3 import ID3

runner = CliRunner()

# Two valid MPEG-1 Layer III frames (128kbps/44.1kHz, 417 bytes each).
_MP3_FRAMES = (bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413) * 2


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    p = tmp_path / "track01.mp3"
    p.write_bytes(_MP3_FRAMES); ID3().save(p)
    monkeypatch.setattr(
        "lyricbuilder.cli.load_config",
        lambda *a, **kw: Config(source_dir=str(tmp_path), cache_dir=str(tmp_path / "cache")),
    )
    res = runner.invoke(app, ["scan", "--source-dir", str(tmp_path), "--dry-run", "--no-embed"])
    assert res.exit_code == 0
    assert not (tmp_path / "track01.lrc").exists()


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
