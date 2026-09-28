import json
from urllib.parse import urlparse


def test_fixture_site_crawl(fixture_site, crawl, tmp_path):
    rows = crawl(fixture_site)
    paths = sorted(urlparse(row["url"]).path for row in rows)
    # /about and /about/ are one page.
    assert paths == ["/", "/about/", "/catalogue/", "/contact.html", "/guides/planting.html", "/guides/watering.html"]
    assert all(row["status"] == 200 for row in rows)
    by_path = {urlparse(row["url"]).path: row for row in rows}
    # The listing keeps all its items, not only the first <article>.
    assert by_path["/catalogue/"]["text_source"] == "trafilatura" and by_path["/catalogue/"]["word_count"] > 150
    assert "Market Lane" not in by_path["/guides/watering.html"]["text"]  # footer
    # The growers' note closes 5 of the 6 pages: site-wide boilerplate, written once.
    boilerplate = json.loads((tmp_path / "job" / "boilerplate.json").read_text(encoding="utf-8"))
    note = "Questions about a plant? Our growers answer every email within one working day."
    assert note in boilerplate["blocks"] and boilerplate["pages_with_text"] == 6
    assert note in by_path["/guides/planting.html"]["text"]  # results.jsonl keeps the full text
    # A normal site answers the made-up address with 404: nothing flagged, no switch to rendering.
    summary = json.loads((tmp_path / "job" / "summary.json").read_text(encoding="utf-8"))
    assert summary["same_page_check"]["status"] == 404 and "/__websitecrawler_check_" in summary["same_page_check"]["url"]
    assert summary["site_notes"] == [] and summary["render_js"] is False and summary["render_js_switched"] is False
    assert all(row["suspicious"] is None and row["rendered"] is False for row in rows)
    # The result line and summary.json say what was marked and removed.
    result = summary["result"]
    assert result == {"pages": 6, "duplicates": 0, "near_duplicates": 0, "boilerplate_blocks": len(boilerplate["blocks"]),
                      "trap_urls_skipped": 0}
    log = (tmp_path / "job" / "job.log").read_text(encoding="utf-8")
    assert f"Result: 6 pages, 0 duplicates, 0 near duplicates, {len(boilerplate['blocks'])} boilerplate blocks, 0 trap URLs skipped" in log
