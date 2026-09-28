import json
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler

from scrapy.http import HtmlResponse, Request

from conftest import serve
from polite_crawler.spiders.site import SiteSpider
from polite_crawler.traps import TrapGuard, trap_rule

TODAY = date(2026, 9, 28)


def rule(path):
    return trap_rule("https://example.com" + path, today=TODAY)


def test_repeated_and_too_many_segments():
    assert rule("/a/a/a/page") == "repeated_segments"
    assert rule("/x/a/b/a/c/a/d/a") == "repeated_segments"  # "a" 4 times
    assert rule("/a/a/b") is None and rule("/a/b/a/c/a") is None  # twice in a row, or 3 times, is fine
    assert rule("/" + "/".join(f"s{i}" for i in range(21))) == "too_many_segments"
    assert rule("/" + "/".join(f"s{i}" for i in range(20))) is None


def test_far_future_dates():
    assert rule("/events/2027/10/01") == "future_date"
    assert rule("/calendar/2027/10") == "future_date"
    assert rule("/events/day-2027-10-01") == "future_date"
    assert rule("/cal?month=2027-10") == "future_date"
    assert rule("/cal?date=2030-01-05&view=day") == "future_date"
    assert rule("/cal?year=2028") == "future_date"
    # Within 12 months, or in the past (archives): requested.
    assert rule("/calendar/2027/09") is None
    assert rule("/cal?date=2027-09-01") is None
    assert rule("/news/1999/01/02/story") is None
    assert rule("/archive?year=1990") is None
    # Numbers that are not dates, or not where dates are looked for.
    assert rule("/products/2031") is None
    assert rule("/2031/05/a/b/c/d") is None  # not in the last three segments
    assert rule("/cal?id=2031-05-01") is None
    assert rule("/x/2027-02-31") is None  # not a real day: ignored, not an error


def test_deep_pagination():
    assert rule("/list?page=501") == "deep_pagination"
    assert rule("/blog/page/9000/") == "deep_pagination"
    assert rule("/list?PG=600&x=1") == "deep_pagination"
    assert rule("/list?page=500") is None and rule("/blog/page/2/") is None and rule("/list?page=last") is None


def test_suspected_traps_are_reported_not_blocked():
    guard = TrapGuard()
    assert all(guard.allow(f"https://example.com/item/{n}?color=c{n}") for n in range(150))
    assert all(guard.allow(f"https://example.com/p{n}") for n in range(3))
    assert not guard.allow("https://example.com/a/a/a")
    report = guard.suspected()
    assert [entry.get("template") or entry.get("parameter") for entry in report] == ["/item/N?color", "color"]
    assert report[0]["count"] == 150 and len(report[0]["examples"]) == 3
    assert guard.skipped == {"repeated_segments": 1}


def test_spider_skips_trap_links_and_counts_them(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    future = (date.today() + timedelta(days=500)).strftime("%Y/%m")
    body = f"""<html><body><a href="/ok">ok</a> <a href="/cal/{future}">next</a>
      <a href="/a/a/a/">loop</a> <a href="/list?page=9999">last</a> <a href="/list?page=9999#x">again</a></body></html>"""
    out = list(spider.parse(HtmlResponse("https://example.com/", body=body.encode(), request=Request("https://example.com/"))))
    assert [r.url for r in out if isinstance(r, Request)] == ["https://example.com/ok"]
    assert spider.traps.skipped == {"future_date": 1, "repeated_segments": 1, "deep_pagination": 1}


class Calendar(BaseHTTPRequestHandler):
    """/cal/YYYY/MM links to the next month, forever, and to a page with a relative link that nests forever."""
    def do_GET(self):
        parts = [p for p in self.path.split("/") if p]
        if self.path == "/":
            month = date.today().replace(day=1)
            body = f'<a href="/cal/{month:%Y/%m}">calendar</a> <a href="/loop/">loop</a>'
        elif parts[:1] == ["cal"]:
            year, month = int(parts[1]), int(parts[2])
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            body = f'<p>Events</p><a href="/cal/{year}/{month:02d}">next month</a>'
        elif parts and all(p == "loop" for p in parts):
            body = '<p>Loop</p><a href="loop/">deeper</a>'
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(f"<html><body>{body}</body></html>".encode())

    def log_message(self, format, *args):
        pass


def test_crawl_stops_at_calendar_and_loop_traps(crawl, tmp_path):
    site = serve(Calendar)
    try:
        rows = crawl(f"http://127.0.0.1:{site.server_port}/", "--max-depth", "0", "--no-sitemap")
    finally:
        site.shutdown()
    calendar = [row for row in rows if "/cal/" in row["url"]]
    assert 12 <= len(calendar) <= 13  # this month up to 12 months ahead
    assert len([row for row in rows if "/loop/" in row["url"]]) == 2  # /loop/ and /loop/loop/
    summary = json.loads((tmp_path / "job" / "summary.json").read_text(encoding="utf-8"))
    assert summary["skipped"] == {"future_date": 1, "repeated_segments": 1}
    assert summary["suspected_traps"] == []
