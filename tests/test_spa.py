"""Sites that answer every address with the same page and draw the real one in the browser
(textifydigitals.com: nginx sends the pre-rendered home page for any path, React redraws it)."""
import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import pytest

from conftest import serve

PAGES = {
    "/": ("Lantern Studio", (
        "Lantern Studio builds booking systems for small clinics, salons and repair shops. Customers pick "
        "a time on their phone, get a reminder the day before, and can move the visit with one tap. Staff "
        "see the whole week on one screen and can block holidays in advance. We host everything in Europe "
        "and answer support mail within one working day, including weekends in the busy season."
    )),
    "/terms": ("Terms of Service", (
        "These terms apply to every account on the booking service. You may cancel at any time and we "
        "refund the unused part of a yearly plan. You keep the rights to your customer list and may export "
        "it whenever you like. We may suspend an account that sends spam through our reminder messages, "
        "after one written warning. Disputes are handled by the courts of the city where we are registered."
    )),
    "/privacy-policy": ("Privacy Policy", (
        "We store the names, phone numbers and visit times your customers enter, and nothing else about "
        "them. Reminder messages go out through one carrier that deletes their content after thirty days. "
        "Backups are encrypted and kept for two weeks. We never sell data, never show advertising, and "
        "delete an account's records within a month of it being closed, unless the law asks us to keep invoices."
    )),
    "/services/sms-api": ("SMS API", (
        "The messaging interface lets developers send reminders from their own software. Each request "
        "carries a key, a phone number in international format and up to three hundred characters of text. "
        "Delivery reports arrive by webhook within a minute. Prices fall with volume, and unused credit "
        "rolls over to the next month. A sandbox number lets you test without paying for real messages."
    )),
}
LINKS = " ".join(f'<a href="{path}">{title}</a>' for path, (title, _) in PAGES.items())
# The same bytes for every path: the home page, then a script that draws the page for
# location.pathname about 300 ms after load, as a client-side router does.
SHELL = f"""<!DOCTYPE html>
<html><head><title>Lantern Studio</title><link rel="canonical" href="/"></head>
<body><nav>{LINKS}</nav><main id="app"><h1>Lantern Studio</h1><p>{PAGES["/"][1]}</p></main>
<script>
const pages = {json.dumps(PAGES)};
setTimeout(() => {{
  const [title, text] = pages[location.pathname] || ["Not found", "There is no page at this address."];
  document.title = title + " | Lantern Studio";
  document.getElementById("app").innerHTML = "<h1>" + title + "</h1><p>" + text + "</p>";
}}, 300);
</script></body></html>""".encode()


class SinglePageApp(BaseHTTPRequestHandler):
    """Answers every path with SHELL and status 200; remembers which paths were asked for."""
    requested = []

    def do_GET(self):
        self.requested.append(urlparse(self.path).path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(SHELL)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def spa_site():
    handler = type("Handler", (SinglePageApp,), {"requested": []})
    site = serve(handler)
    site.requested = handler.requested
    yield site
    site.shutdown()


def seed(site):
    return f"http://127.0.0.1:{site.server_port}/"


def by_path(rows):
    return {urlparse(row["url"]).path: row for row in rows}


def test_rendering_waits_for_the_page_drawn_in_the_browser(spa_site, crawl):
    rows = by_path(crawl(seed(spa_site), "--no-sitemap", "--render-js"))
    assert sorted(rows) == sorted(PAGES)
    for path, (title, text) in PAGES.items():
        assert rows[path]["title"] == f"{title} | Lantern Studio"
        assert text.split(".")[0] in rows[path]["text"]
        assert rows[path]["duplicate_of"] is None


def test_without_rendering_every_address_gives_the_home_page(spa_site, crawl, tmp_path):
    rows = by_path(crawl(seed(spa_site), "--no-sitemap"))
    assert sorted(rows) == sorted(PAGES)
    assert {row["title"] for row in rows.values()} == {"Lantern Studio"}
    assert all(row["duplicate_of"] == seed(spa_site) for path, row in rows.items() if path != "/")


class PollsForever(BaseHTTPRequestHandler):
    """A page that asks the server for news every 200 ms, so the network never goes quiet."""
    def do_GET(self):
        if self.path.startswith("/poll"):
            self.send_response(204)
            self.end_headers()
            return
        body = b"""<!DOCTYPE html><html><head><title>Live scores</title></head><body><p id="score">loading</p>
<script>
document.getElementById("score").textContent = "Drawn by the script before the timeout";
setInterval(() => fetch("/poll?" + Date.now()), 200);
</script></body></html>"""
        self.send_response(200 if self.path == "/" else 404)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def test_a_page_that_never_goes_quiet_is_still_saved(crawl):
    site = serve(PollsForever)
    try:
        started = time.monotonic()
        rows = crawl(f"http://127.0.0.1:{site.server_port}/", "--no-sitemap", "--render-js")
        elapsed = time.monotonic() - started
    finally:
        site.shutdown()
    assert [row["title"] for row in rows] == ["Live scores"]
    assert "Drawn by the script before the timeout" in rows[0]["text"]
    assert elapsed < 100  # the settle wait gives up after 10 s; the page is not dropped
