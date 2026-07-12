from lyricbuilder.cache import Cache


def test_key_is_normalized_case_punct_whitespace(tmp_path):
    k1 = Cache.key("晴天", "周杰伦")
    k2 = Cache.key(" 晴天  ", "周杰伦")
    assert k1 == k2
    assert Cache.key("SUNNY", "Jay") == Cache.key("sunny", "jay")


def test_key_stable_across_runs():
    a = Cache.key("A", "B")
    b = Cache.key("A", "B")
    assert a == b and len(a) > 0


def test_get_miss_returns_none(tmp_path):
    c = Cache(tmp_path)
    assert c.get("Unknown", "Nobody") is None


def test_put_then_get_roundtrip(tmp_path):
    c = Cache(tmp_path)
    result = {"matched": True, "type": "lrc", "text": "[00:00]hi", "source": "lrclib"}
    c.put("晴天", "周杰伦", result)
    assert c.get("晴天", "周杰伦") == result


def test_negative_cache_stored(tmp_path):
    c = Cache(tmp_path)
    c.put("Nope", "Nobody", {"matched": False})
    assert c.get("Nope", "Nobody") == {"matched": False}


def test_corrupt_index_does_not_crash(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text("{ not valid json", encoding="utf-8")
    c = Cache(tmp_path)
    assert c.get("Any", "Thing") is None
    # put still works after corrupt load
    c.put("A", "B", {"matched": True, "type": "plain", "text": "x", "source": "s"})
    assert c.get("A", "B")["matched"] is True


def test_concurrent_write_same_key_tolerant(tmp_path):
    c = Cache(tmp_path)
    for _ in range(5):
        c.put("Same", "Artist", {"matched": True, "type": "lrc", "text": "t", "source": "s"})
    assert c.get("Same", "Artist")["text"] == "t"


def test_get_returns_independent_copy(tmp_path):
    c = Cache(tmp_path)
    result = {"matched": True, "type": "lrc", "text": "[00:00]hi", "source": "lrclib"}
    c.put("晴天", "周杰伦", result)
    got = c.get("晴天", "周杰伦")
    assert got == result
    got["text"] = "MUTATED"
    got["matched"] = False
    again = c.get("晴天", "周杰伦")
    assert again == result
    assert again["text"] == "[00:00]hi"
    assert again["matched"] is True
