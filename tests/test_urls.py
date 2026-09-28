from scrapy.http import HtmlResponse, Request

from polite_crawler.spiders.site import SiteSpider, clean_url, page_key

HEX = "0123456789abcdef0123456789ABCDEF"


def test_clean_url_drops_tracking_and_session_ids_only():
    assert clean_url("https://x.test/a?utm_source=n&id=5&gclid=1#top") == "https://x.test/a?id=5#top"
    assert clean_url("https://x.test/a;jsessionid=AB12?x=1") == "https://x.test/a?x=1"
    assert clean_url("https://x.test/a?PHPSESSID=9f&q=red%20shoes&SessionId=1") == "https://x.test/a?q=red%20shoes"
    assert clean_url(f"https://x.test/a?sid={HEX}&b=2") == "https://x.test/a?b=2"
    # "sid" that is not a session id (a store id, say) stays.
    assert clean_url("https://x.test/a?sid=42") == "https://x.test/a?sid=42"
    # Everything else is left exactly as found.
    assert clean_url("https://x.test/A/b/?z=1&a=2&a=1") == "https://x.test/A/b/?z=1&a=2&a=1"


def test_page_key_merges_url_variants():
    same = [
        "https://example.com/shop",
        "https://example.com/shop/",
        "HTTPS://WWW.Example.COM:443/shop",
        "https://example.com/shop/index.html",
        "https://example.com/shop/index.php#reviews",
        "https://example.com/shop?utm_campaign=x",
        "https://example.com/shop;jsessionid=1A2B",
    ]
    assert {page_key(url) for url in same} == {"https://example.com/shop"}
    assert page_key("https://example.com/p?b=2&a=1") == page_key("https://example.com/p?a=1&b=2")
    assert page_key("https://example.com/") == page_key("https://example.com") == page_key("https://www.example.com/index.htm")
    # Different pages keep different keys.
    assert page_key("https://example.com/Shop") != page_key("https://example.com/shop")  # path case kept
    assert page_key("http://example.com/shop") != page_key("https://example.com/shop")
    assert page_key("https://example.com:8443/shop") != page_key("https://example.com/shop")
    assert page_key("https://example.com/p?a=1") != page_key("https://example.com/p?a=2")


def parse(spider, url, body):
    request = Request(url, headers={"Referer": "https://example.com/"})
    return list(spider.parse(HtmlResponse(url, body=body, request=request)))


def test_spider_requests_one_url_per_key(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    out = parse(spider, "https://example.com/", b"""<html><body>
      <a href="/a">a</a> <a href="/a/">a again</a> <a href="https://www.example.com/a/index.html">and again</a>
      <a href="/b;jsessionid=XYZ">b</a> <a href="/b?PHPSESSID=1">b again</a> <a href="/">home</a></body></html>""")
    assert [r.url for r in out if isinstance(r, Request)] == ["https://example.com/a", "https://example.com/b"]
    # The same link on the next page is not requested again.
    out = parse(spider, "https://example.com/c", b'<html><body><a href="/a/">a</a></body></html>')
    assert [r for r in out if isinstance(r, Request)] == []


def test_spider_follows_canonical_to_the_real_page(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    twin = b'<html><head><link rel="canonical" href="/product"></head><body><p>Red shoe</p></body></html>'
    out = parse(spider, "https://example.com/product?color=red", twin)
    assert out[0]["text"] == "Red shoe"  # the variant keeps its row and text
    assert [r.url for r in out if isinstance(r, Request)] == ["https://example.com/product"]
    # A canonical pointing at the page itself (or off-site) requests nothing.
    self_canonical = b'<html><head><link rel="canonical" href="https://www.example.com/x/"></head><body></body></html>'
    assert [r for r in parse(spider, "https://example.com/x", self_canonical) if isinstance(r, Request)] == []
    offsite = b'<html><head><link rel="canonical" href="https://other.test/y"></head><body></body></html>'
    assert [r for r in parse(spider, "https://example.com/y", offsite) if isinstance(r, Request)] == []


def test_resume_counts_rows_not_keys(tmp_path):
    rows = ['{"url": "https://example.com/a"}', '{"url": "https://example.com/a/"}', '{"url": "https://example.com/b"}']
    (tmp_path / "results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    assert spider.rows == 3 and spider.saved_urls == {"https://example.com/a", "https://example.com/b"}
