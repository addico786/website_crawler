from urllib.parse import urlparse


def test_fixture_site_crawl(fixture_site, crawl):
    rows = crawl(fixture_site)
    paths = sorted(urlparse(row["url"]).path for row in rows)
    # /about and /about/ are one page.
    assert paths == ["/", "/about/", "/catalogue/", "/contact.html", "/guides/planting.html", "/guides/watering.html"]
    assert all(row["status"] == 200 for row in rows)
    by_path = {urlparse(row["url"]).path: row for row in rows}
    # The listing keeps all its items, not only the first <article>.
    assert by_path["/catalogue/"]["text_source"] == "trafilatura" and by_path["/catalogue/"]["word_count"] > 150
    assert "Market Lane" not in by_path["/guides/watering.html"]["text"]  # footer
