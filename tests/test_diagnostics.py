import hashlib
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import pytest

from conftest import serve

HOME = b'<html><head><title>Home</title></head><body><p>Start here.</p><a href="/old">the guide</a></body></html>'
NEW = (b"<html><head><title>New guide</title></head><body><p>The guide moved here.</p>"
       b"<script>document.body.dataset.drawn = 'by the script';</script></body></html>")


class Moved(BaseHTTPRequestHandler):
    """/ links to /old, which moved to /new for good."""
    def do_GET(self):
        if self.path == "/old":
            self.send_response(301)
            self.send_header("Location", "/new")
            self.end_headers()
            return
        body = {"/": HOME, "/new": NEW}.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body or b"Not found")

    def log_message(self, format, *args):
        pass


@pytest.fixture
def moved_site():
    site = serve(Moved)
    yield f"http://127.0.0.1:{site.server_port}"
    site.shutdown()


def test_rows_say_what_was_asked_for_and_what_came_back(moved_site, crawl):
    rows = {urlparse(row["url"]).path: row for row in crawl(moved_site + "/", "--no-sitemap")}
    assert sorted(rows) == ["/", "/new"]
    moved = rows["/new"]
    assert moved["requested_url"] == moved_site + "/old"
    assert moved["final_url"] == moved["url"] == moved_site + "/new"
    assert moved["redirect_chain"] == [moved_site + "/old"]
    assert moved["response_bytes"] == len(NEW) and moved["response_sha256"] == hashlib.sha256(NEW).hexdigest()
    assert moved["rendered"] is False
    home = rows["/"]
    assert home["requested_url"] == home["final_url"] == moved_site + "/" and home["redirect_chain"] == []
    assert home["response_sha256"] == hashlib.sha256(HOME).hexdigest()


def test_rendered_rows_hash_the_rendered_html(moved_site, crawl):
    rows = {urlparse(row["url"]).path: row for row in crawl(moved_site + "/", "--no-sitemap", "--render-js")}
    assert sorted(rows) == ["/", "/new"]
    assert all(row["rendered"] is True for row in rows.values())
    # The HTML the browser ended up with (the script marked <body>), not the bytes sent.
    moved = rows["/new"]
    assert moved["response_sha256"] != hashlib.sha256(NEW).hexdigest() and moved["response_bytes"] != len(NEW)
    assert moved["requested_url"] == moved_site + "/old" and moved["redirect_chain"] == [moved_site + "/old"]
