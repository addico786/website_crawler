from scrapy.http import HtmlResponse

import polite_crawler.maintext as maintext
from conftest import FIXTURE_SITE
from polite_crawler.maintext import main_text


def fixture_page(path):
    response = HtmlResponse("http://127.0.0.1/", body=(FIXTURE_SITE / path).read_bytes())
    return response.text, response.selector.root


def test_listing_page_keeps_every_item():
    # Several <article>s and no <main>: 1.1.1 kept only the first article (about 20 words).
    text, source = main_text(*fixture_page("catalogue/index.html"))
    assert source == "trafilatura"
    assert len(text.split()) > 150
    for words in ("bathroom window", "moss pole", "completely dry", "£8.75"):
        assert words in text


def test_menus_and_footer_are_left_out_one_block_per_line():
    text, source = main_text(*fixture_page("guides/planting.html"))
    assert source == "trafilatura"
    lines = text.splitlines()
    assert lines[0] == "Planting guide"
    assert "Step by step" in lines
    assert any(line.startswith("Water the plant the day before.") and line.endswith("water until it drains.") for line in lines)
    assert "Watering guide" not in text and "Market Lane" not in text


def test_short_page():
    text, _ = main_text(*fixture_page("contact.html"))
    assert "hello@fern-and-stone.test" in text


def test_fallback_when_trafilatura_keeps_too_little_or_fails(monkeypatch):
    html, root = fixture_page("guides/watering.html")
    monkeypatch.setattr(maintext.trafilatura, "extract", lambda *a, **k: "Watering guide")
    text, source = main_text(html, root)
    assert source == "fallback" and "empty the saucer" in text and "Watering guide" in text.splitlines()
    assert "Market Lane" not in text  # the fallback also leaves out nav, header and footer

    def broken(*args, **kwargs):
        raise ValueError("parser bug")
    monkeypatch.setattr(maintext.trafilatura, "extract", broken)
    assert main_text(html, root)[1] == "fallback"
    monkeypatch.setattr(maintext.trafilatura, "extract", lambda *a, **k: None)
    assert main_text(html, root)[1] == "fallback"


def test_huge_pages_skip_trafilatura(monkeypatch):
    def not_called(*args, **kwargs):
        raise AssertionError("trafilatura should not run on bodies over 5 MB")
    monkeypatch.setattr(maintext.trafilatura, "extract", not_called)
    html = "<html><body><p>" + "word " * 1_100_000 + "</p></body></html>"
    response = HtmlResponse("http://127.0.0.1/", body=html.encode())
    text, source = main_text(response.text, response.selector.root)
    assert source == "fallback" and len(text.split()) == 1_100_000
