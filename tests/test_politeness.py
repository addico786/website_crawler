import time
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

from conftest import serve
from polite_crawler.middlewares import retry_after_seconds


def test_retry_after_values():
    assert retry_after_seconds("120") == 120
    in_a_minute = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60), usegmt=True)
    assert 55 < retry_after_seconds(in_a_minute) <= 60
    assert retry_after_seconds(format_datetime(datetime(2000, 1, 1, tzinfo=timezone.utc), usegmt=True)) == 0
    assert retry_after_seconds("soon") is None


class PoliteSite(BaseHTTPRequestHandler):
    """robots.txt asks for 2 s between requests; the home page first answers 429, Retry-After: 3."""
    log = []

    def do_GET(self):
        self.log.append((self.path, time.monotonic(), self.headers.get("User-Agent")))
        if self.path == "/robots.txt":
            self.reply(200, b"User-agent: *\nCrawl-delay: 2\n", "text/plain")
        elif self.path == "/" and sum(1 for path, _, _ in self.log if path == "/") == 1:
            self.reply(429, b"slow down", "text/plain", {"Retry-After": "3"})
        elif self.path in ("/", "/a", "/b"):
            self.reply(200, b'<html><body><p>Page</p><a href="/a">a</a> <a href="/b">b</a></body></html>', "text/html")
        else:
            self.reply(404, b"no", "text/plain")

    def reply(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def test_crawl_delay_retry_after_and_user_agent(crawl, tmp_path):
    PoliteSite.log = []
    site = serve(PoliteSite)
    try:
        # --no-sitemap: robots.txt is still fetched, for its rules and Crawl-delay.
        rows = crawl(f"http://127.0.0.1:{site.server_port}/", "--no-sitemap", "--delay", "0")
    finally:
        site.shutdown()
    log = (tmp_path / "job" / "job.log").read_text(encoding="utf-8")
    assert sorted(row["url"].rsplit("/", 1)[-1] for row in rows) == ["", "a", "b"]
    assert "Crawl-delay: 2; waiting 2.0 s" in log
    assert "Retry-After: 3; waiting 3 s" in log

    paths = [path for path, _, _ in PoliteSite.log]
    times = [when for _, when, _ in PoliteSite.log]
    assert paths[0] == "/robots.txt" and paths.count("/") == 2
    assert {agent for _, _, agent in PoliteSite.log} == {"WebsiteCrawler (+https://github.com/addico786/website_crawler)"}
    retry = paths.index("/", paths.index("/") + 1)
    assert times[retry] - times[retry - 1] >= 2.9  # Retry-After
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    assert min(gaps) >= 1.9  # Crawl-delay, with no jitter below it
