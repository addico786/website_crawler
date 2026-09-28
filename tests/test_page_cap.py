import time
from http.server import BaseHTTPRequestHandler

import pytest

from conftest import serve


class HundredPages(BaseHTTPRequestHandler):
    """/ and /p/1 ... /p/99, each linking to every page; a little latency keeps requests in flight."""
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/p/"):
            time.sleep(0.05)
            links = " ".join(f'<a href="/p/{n}">page {n}</a>' for n in range(1, 100))
            body = f"<html><head><title>{self.path}</title></head><body><p>Page {self.path}</p>{links}</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def hundred_pages():
    site = serve(HundredPages)
    yield f"http://127.0.0.1:{site.server_port}/"
    site.shutdown()


def test_page_cap_is_exact(hundred_pages, crawl, tmp_path):
    rows = crawl(hundred_pages, "--max-pages", "30", "--concurrency", "8", "--no-sitemap")
    assert len(rows) == 30
    # Resuming the job: earlier rows count towards the cap, so nothing more is saved.
    rows = crawl(hundred_pages, "--max-pages", "30", "--concurrency", "8", "--no-sitemap")
    assert len(rows) == 30
    # A higher cap on the same job adds only the difference.
    rows = crawl(hundred_pages, "--max-pages", "35", "--concurrency", "8", "--no-sitemap")
    assert len(rows) == 35 and len({row["url"] for row in rows}) == 35


def test_page_cap_with_javascript_rendering(hundred_pages, crawl):
    rows = crawl(hundred_pages, "--max-pages", "30", "--concurrency", "8", "--no-sitemap", "--render-js")
    assert 0 < len(rows) <= 30
