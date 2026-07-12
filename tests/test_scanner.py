from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1
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
