import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'aifc' is deprecated")
import aifc
from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.id3 import ID3

from lyricbuilder.models import Clue, LyricResult
from lyricbuilder.tagger import Tagger


# Two valid MPEG-1 Layer III frames (128kbps/44.1kHz, 417 bytes each).
_MP3_FRAMES = (bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413) * 2


def _make_mp3(path: Path):
    path.write_bytes(_MP3_FRAMES)
    ID3().save(path)  # attach an empty ID3v2 block, preserving the MPEG frames


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


def _make_aiff(path: Path):
    # Valid AIFF container via stdlib aifc + empty ID3 block (mirror of _make_mp3).
    with open(path, "wb") as fh:
        with aifc.open(fh, "w") as w:
            w.aiff(); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
            w.writeframesraw(b"\x00\x00")
    AIFF(path).save()  # ensure an ID3 chunk exists for embedding


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
