import warnings  # add to existing imports at top
warnings.filterwarnings("ignore", category=DeprecationWarning, message="'aifc' is deprecated")
import aifc       # add to existing imports at top
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.aiff import AIFF  # add to existing imports at top
from mutagen.id3 import ID3, TIT2, TPE1  # TIT2/TPE1 already? no — only ID3 is imported at line 3; add TIT2, TPE1
from mutagen.mp4 import MP4

from lyricbuilder.scanner import Scanner


def _make_mp3(path: Path, title: str | None, artist: str | None):
    # An empty-bytes file is NOT a valid MPEG stream, so `MP3(path)` raises.
    # Write ID3 tags directly via mutagen.id3.ID3 — works without MPEG audio.
    path.write_bytes(b"")
    id3 = ID3()
    if title:
        id3.add(TIT2(encoding=3, text=[title]))
    if artist:
        id3.add(TPE1(encoding=3, text=[artist]))
    id3.save(path)


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
