import pytest
import httpx
import respx
from lyricbuilder.models import LyricResult, TransientSourceError
from sources.lrclib import LRCLibSource

BASE = "https://lrclib.net/api/get"


@respx.mock
def test_returns_synced_lrc_on_hit():
    respx.get(BASE).respond(200, json={"syncedLyrics": "[00:00]晴天", "plainLyrics": None})
    src = LRCLibSource()
    r = src.get("晴天", "周杰伦")
    assert r.matched is True
    assert r.type == "lrc"
    assert r.text == "[00:00]晴天"
    assert r.source == "lrclib"


@respx.mock
def test_returns_plain_when_only_plain_available():
    respx.get(BASE).respond(200, json={"syncedLyrics": None, "plainLyrics": ["line1"]})
    src = LRCLibSource()
    r = src.get("A", "B")
    assert r.matched is True
    assert r.type == "plain"
    assert "line1" in r.text


@respx.mock
def test_returns_unmatched_on_404():
    respx.get(BASE).respond(404)
    src = LRCLibSource()
    r = src.get("A", "B")
    assert r.matched is False
    assert r.type is None


@respx.mock
def test_raises_transient_on_timeout():
    respx.get(BASE).mock(side_effect=httpx.TimeoutException("slow"))
    src = LRCLibSource(timeout=0.01, retries=1)
    with pytest.raises(TransientSourceError):
        src.get("A", "B")


@respx.mock
def test_raises_transient_on_429_after_retry():
    respx.get(BASE).respond(429)
    src = LRCLibSource(timeout=1.0, retries=2)
    with pytest.raises(TransientSourceError):
        src.get("A", "B")
