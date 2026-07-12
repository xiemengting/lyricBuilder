import respx
from sources.netease import NeteaseSource

SEARCH = "https://music.163.com/api/search/get"
LYRIC = "https://music.163.com/api/song/lyric"


@respx.mock
def test_returns_synced_lrc():
    respx.get(SEARCH).respond(200, json={"result": {"songs": [{"id": 42, "name": "晴天", "artists": [{"name": "周杰伦"}]}]}})
    respx.get(LYRIC).respond(200, json={"lrc": {"lyric": "[00:01]晴天"}, "tlyric": {"lyric": None}})
    r = NeteaseSource().get("晴天", "周杰伦")
    assert r.matched and r.type == "lrc" and r.source == "netease"


@respx.mock
def test_returns_plain_when_no_lrc():
    respx.get(SEARCH).respond(200, json={"result": {"songs": [{"id": 42, "name": "晴天", "artists": [{"name": "周杰伦"}]}]}})
    respx.get(LYRIC).respond(200, json={"lrc": None, "tlyric": None})
    r = NeteaseSource().get("晴天", "周杰伦")
    assert r.matched is False


@respx.mock
def test_unmatched_when_search_empty():
    respx.get(SEARCH).respond(200, json={"result": {"songs": []}})
    r = NeteaseSource().get("A", "B")
    assert r.matched is False


@respx.mock
def test_unmatched_on_http_error():
    respx.get(SEARCH).respond(500)
    r = NeteaseSource(retries=1).get("A", "B")
    assert r.matched is False
