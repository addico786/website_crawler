from urllib.parse import urlparse


def test_fixture_site_crawl(fixture_site, crawl):
    rows = crawl(fixture_site)
    paths = sorted(urlparse(row["url"]).path for row in rows)
    # /about and /about/ are one page.
    assert paths == ["/", "/about/", "/catalogue/", "/contact.html", "/guides/planting.html", "/guides/watering.html"]
    assert all(row["status"] == 200 for row in rows)
