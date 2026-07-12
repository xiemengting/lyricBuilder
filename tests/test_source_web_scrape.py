import pytest
import respx
from lyricbuilder.models import TransientSourceError
from sources.web_scrape import WebScrapeSource

SEARCH = "https://example-lyrics.test/search"


@respx.mock
def test_returns_plain_from_parsed_html():
    html = """
    <div class="lyrics"><p>line one</p><p>line two</p></div>
    """
    respx.get("https://example-lyrics.test/search").respond(200, text=html)
    r = WebScrapeSource().get("晴天", "周杰伦")
    assert r.matched is True
    assert r.type == "plain"
    assert "line one" in r.text and "line two" in r.text
    assert r.source == "scrape"


@respx.mock
def test_unmatched_when_selector_misses():
    respx.get("https://example-lyrics.test/search").respond(200, text="<html><body>nope</body></html>")
    r = WebScrapeSource().get("A", "B")
    assert r.matched is False


@respx.mock
def test_raises_transient_on_http_error():
    respx.get("https://example-lyrics.test/search").respond(500)
    with pytest.raises(TransientSourceError):
        WebScrapeSource(retries=1).get("A", "B")


def test_unmatched_without_title():
    r = WebScrapeSource().get(None, "B")
    assert r.matched is False
