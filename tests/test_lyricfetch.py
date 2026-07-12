from pathlib import Path
from lyricbuilder.models import Clue, LyricResult
from lyricbuilder.cache import Cache
from lyricbuilder.lyricfetch import LyricFetcher


class _Fake:
    def __init__(self, name, result):
        self.name = name
        self._r = result
    def get(self, title, artist):
        return self._r


def test_returns_first_source_hit_and_skips_rest():
    called = []
    class A:
        name = "a"
        def get(self, t, a):
            called.append("a"); return LyricResult(True, "lrc", "x", "a", {})
    class B:
        name = "b"
        def get(self, t, a):
            called.append("b"); return LyricResult(True, "lrc", "y", "b", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A(), B()]).fetch(clue)
    assert r.matched and r.source == "a" and called == ["a"]


def test_falls_through_to_next_on_miss():
    class A:
        name = "a"
        def get(self, t, a): return LyricResult(False, None, None, "a", {})
    class B:
        name = "b"
        def get(self, t, a): return LyricResult(True, "plain", "y", "b", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A(), B()]).fetch(clue)
    assert r.source == "b" and r.type == "plain"


def test_all_miss_returns_unmatched():
    class A:
        name = "a"
        def get(self, t, a): return LyricResult(False, None, None, "a", {})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([A()]).fetch(clue)
    assert r.matched is False


def test_cache_hit_skips_sources(tmp_path):
    class Exploding:
        name = "boom"
        def get(self, t, a): raise AssertionError("should not be called")
    cache = Cache(tmp_path)
    cache.put("T", "A", {"matched": True, "type": "lrc", "text": "cached", "source": "lrclib"})
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    r = LyricFetcher([Exploding()], cache=cache).fetch(clue)
    assert r.text == "cached"


def test_negative_result_cached(tmp_path):
    class A:
        name = "a"
        calls = 0
        def get(self, t, a):
            A.calls += 1; return LyricResult(False, None, None, "a", {})
    cache = Cache(tmp_path)
    clue = Clue(Path("s.mp3"), "mp3", "T", "A", "tag")
    f = LyricFetcher([A()], cache=cache)
    f.fetch(clue); f.fetch(clue)
    assert A.calls == 1


def test_none_clue_returns_unmatched_without_calling_sources():
    class Boom:
        name = "b"
        def get(self, t, a): raise AssertionError("nope")
    clue = Clue(Path("track01.mp3"), "mp3", None, None, "none")
    r = LyricFetcher([Boom()]).fetch(clue)
    assert r.matched is False
