"""Sites that answer every address with the same page and draw the real one in the browser
(textifydigitals.com: nginx sends the pre-rendered home page for any path, React redraws it)."""
import hashlib
import json
import pickle
import shutil
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import pytest
from scrapy.http import HtmlResponse, Request
from scrapy.utils.request import request_from_dict

from conftest import serve
from polite_crawler.spiders.site import SiteSpider, settle

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
# Listed only in the sitemap, which the crawl reads before the start page decides it must render.
UNLINKED = {"/about-us": ("About Us", (
    "Four of us started the studio after years of fixing booking problems for friends who run small "
    "shops. We work from a shared office above a bakery, meet every client in person at least once, and "
    "publish our prices on the website. Most of our customers found us through another customer, which "
    "is the only kind of marketing we have ever paid for, in coffee and cake."
))}
LINKS = " ".join(f'<a href="{path}">{title}</a>' for path, (title, _) in PAGES.items())
# The same bytes for every path: the home page, then a script that draws the page for
# location.pathname about 300 ms after load, as a client-side router does.
SHELL = f"""<!DOCTYPE html>
<html><head><title>Lantern Studio</title><link rel="canonical" href="/"></head>
<body><nav>{LINKS}</nav><main id="app"><h1>Lantern Studio</h1><p>{PAGES["/"][1]}</p></main>
<script>
const pages = {json.dumps(PAGES | UNLINKED)};
setTimeout(() => {{
  const [title, text] = pages[location.pathname] || ["Not found", "There is no page at this address."];
  document.title = title + " | Lantern Studio";
  document.getElementById("app").innerHTML = "<h1>" + title + "</h1><p>" + text + "</p>";
}}, 300);
</script></body></html>""".encode()


class SinglePageApp(BaseHTTPRequestHandler):
    """Answers every path but /sitemap.xml with SHELL and status 200; remembers which paths were asked for.
    home_delay: seconds to wait before answering /."""
    requested = []
    home_delay = 0

    def do_GET(self):
        path = urlparse(self.path).path
        self.requested.append(path)
        if path == "/":
            time.sleep(self.home_delay)
        body, kind = SHELL, "text/html; charset=utf-8"
        if path == "/sitemap.xml":
            base = f"http://127.0.0.1:{self.server.server_port}"
            locs = "".join(f"<url><loc>{base}{page}</loc></url>" for page in [*PAGES, *UNLINKED])
            body = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'.encode()
            kind = "application/xml"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

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


def summary(job):
    return json.loads((job / "summary.json").read_text(encoding="utf-8"))


def check_requests(site):
    return [path for path in site.requested if path.startswith("/__websitecrawler_check_")]


def test_without_a_browser_every_address_gives_the_home_page(spa_site, crawl, tmp_path):
    # No Chromium: the switch to rendering fails, and the crawl goes on without it and says so.
    rows = by_path(crawl(seed(spa_site), "--no-sitemap", env={"PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "no-browser")}))
    assert sorted(rows) == sorted(PAGES)
    assert {row["title"] for row in rows.values()} == {"Lantern Studio"}
    assert all(row["duplicate_of"] == seed(spa_site) for path, row in rows.items() if path != "/")
    assert {row["response_sha256"] for row in rows.values()} == {summary(tmp_path / "job")["same_page_check"]["response_sha256"]}
    assert all(row["suspicious"] == "SAME_RESPONSE" and row["rendered"] is False for row in rows.values())
    result = summary(tmp_path / "job")
    assert result["site_notes"][0] == "same_page_for_every_address"
    assert result["render_js"] is False and result["render_js_switched"] is False
    log = (tmp_path / "job" / "job.log").read_text(encoding="utf-8")
    assert "This site answers every address with the same page (a single-page app)." in log
    assert "Render JavaScript is not available; pages will look the same. Install it from the dashboard." in log
    assert result["result"]["suspicious"] == 4 and "4 suspicious (same page for different addresses)" in log
    # Every page names / as its canonical (the app never changes it): a fault of the site, reported.
    assert result["site_notes"] == ["same_page_for_every_address", "canonical_to_home"]
    assert "3 pages name the home page as their canonical (a site problem)" in log


def test_the_crawl_switches_to_rendering_and_a_resume_keeps_it(spa_site, crawl, tmp_path):
    job = tmp_path / "job"
    # A slow start page: the sitemap's pages are found before it arrives, and must wait for it.
    spa_site.RequestHandlerClass.home_delay = 4
    rows = by_path(crawl(seed(spa_site), "--max-pages", "5", "--concurrency", "4"))
    # Every page, rendered, the sitemap's too: the made-up address is not a row and does not count toward the cap.
    assert sorted(rows) == sorted(PAGES | UNLINKED)
    for path, (title, _) in (PAGES | UNLINKED).items():
        assert rows[path]["title"] == f"{title} | Lantern Studio" and rows[path]["rendered"] is True
        assert rows[path]["duplicate_of"] is None and rows[path]["suspicious"] is None
    assert len({row["response_sha256"] for row in rows.values()}) == 5
    first = summary(job)
    assert first["same_page_check"]["status"] == 200 and first["site_notes"][0] == "same_page_for_every_address"
    assert first["render_js"] is True and first["render_js_switched"] is True
    log = (job / "job.log").read_text(encoding="utf-8")
    assert "Switched to Render JavaScript." in log and "not available" not in log
    # Rendered, the pages still name / as their canonical: the app never updates it.
    assert first["site_notes"] == ["same_page_for_every_address", "canonical_to_home"]
    assert "4 pages name the home page as their canonical (a site problem)" in log
    assert len(check_requests(spa_site)) == 1

    # Resumed without --render-js: no second check and no second switch, still rendering, nothing saved twice.
    spa_site.RequestHandlerClass.home_delay = 0
    assert len(crawl(seed(spa_site), "--max-pages", "5")) == 5
    resumed = (job / "job.log").read_text(encoding="utf-8").rsplit("Scrapy 2.", 1)[1]
    assert "made-up address" not in resumed and "Switched" not in resumed
    assert len(check_requests(spa_site)) == 1
    assert summary(job)["same_page_check"] == first["same_page_check"] and summary(job)["render_js"] is True


def test_a_resumed_job_keeps_the_rendering_decision(tmp_path):
    check = {"url": "https://example.com/__websitecrawler_check_0", "final_url": "https://example.com/__websitecrawler_check_0",
             "status": 200, "response_sha256": "ab" * 32}
    (tmp_path / "summary.json").write_text(json.dumps({"same_page_check": check, "site_notes": [
        "same_page_for_every_address", "canonical_to_home"], "render_js_switched": True}), encoding="utf-8")
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    assert spider.render_js and spider.request("https://example.com/terms").meta["playwright"]
    assert spider.site_check == check and spider.fallback_sha256() == "ab" * 32
    assert spider.site_notes == ["same_page_for_every_address"]  # the end of the crawl works out the others again
    # An earlier switch that failed (no browser) was written back as not switched: crawl without rendering.
    (tmp_path / "summary.json").write_text(json.dumps({"same_page_check": check, "render_js_switched": False}), encoding="utf-8")
    assert not SiteSpider(start_url="https://example.com", job_dir=str(tmp_path)).render_js


def test_resumable_requests_can_be_written_to_disk(tmp_path):
    # JOBDIR keeps pending requests on disk; the rendered start page must pickle, errback and page methods included.
    spider = SiteSpider(start_url="http://127.0.0.1:9/", job_dir=str(tmp_path), render_js="True")
    request = spider.seed_request()
    restored = request_from_dict(pickle.loads(pickle.dumps(request.to_dict(spider=spider), protocol=4)), spider=spider)
    assert restored.errback == spider.seed_failed and restored.callback == spider.parse
    assert restored.meta["seed"] and restored.meta["playwright_page_methods"][0].method is settle


def test_same_response_is_only_flagged_for_pages_that_should_differ(tmp_path):
    spider = SiteSpider(start_url="https://example.com", job_dir=str(tmp_path))
    spider.site_check = {"url": "https://example.com/__websitecrawler_check_0", "final_url": "https://example.com/__websitecrawler_check_0",
                         "status": 404, "response_sha256": hashlib.sha256(b"Not found").hexdigest()}

    def row(path, body, status=200):
        url = f"https://example.com{path}"
        return spider.item(HtmlResponse(url, status=status, body=body, request=Request(url)), "")

    # A normal site: its 404 page for the made-up address, and for two broken links, is not suspicious.
    assert row("/", b"<p>Home</p>")["suspicious"] is None
    assert row("/gone", b"Not found", 404)["suspicious"] is None and row("/lost", b"Not found", 404)["suspicious"] is None
    assert row("/index.html", b"<p>Home</p>")["suspicious"] is None  # the same page, by its key
    assert row("/about", b"<p>Home</p>")["suspicious"] == "SAME_RESPONSE"  # another page, the same bytes
    # A site that sends 200 and one page for an address that cannot exist.
    spider.site_check |= {"status": 200, "response_sha256": hashlib.sha256(b"<p>App</p>").hexdigest()}
    assert row("/terms", b"<p>App</p>")["suspicious"] == "SAME_RESPONSE"
    # ...but not when the made-up address was sent on to another page.
    spider.site_check |= {"final_url": "https://example.com/"}
    assert row("/privacy", b"<p>App</p>")["suspicious"] == "SAME_RESPONSE"  # /terms already had these bytes
    assert spider.fallback_sha256() is None


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


def test_the_dashboard_says_to_turn_on_rendering():
    from fastapi.testclient import TestClient

    from server import BASE_DIR, JOBS_DIR, app

    client = TestClient(app, base_url="http://127.0.0.1:8000")
    job = JOBS_DIR / "test_same_page_note"
    job.mkdir(parents=True, exist_ok=True)
    try:
        (job / "summary.json").write_text(json.dumps({"site_notes": ["same_page_for_every_address"], "render_js": False}))
        detail = client.get("/api/jobs/test_same_page_note").json()
        assert detail["summary"]["site_notes"] == ["same_page_for_every_address"] and detail["summary"]["render_js"] is False
    finally:
        shutil.rmtree(job, ignore_errors=True)
    page = client.get("/").text
    assert "This site sends the same page for every address. Turn on Render JavaScript." in page
    script = (BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert 'notes.includes("same_page_for_every_address") && !summary.render_js' in script


def test_canonical_to_home_needs_three_pages_and_half_of_them(tmp_path):
    spider = SiteSpider(start_url="https://www.example.com/", job_dir=str(tmp_path))

    def rows(to_home, others, status=200):
        home = [{"url": "https://www.example.com/", "status": 200, "canonical_url": "https://www.example.com/"}]
        return home + [
            {"url": f"https://www.example.com/p{n}", "status": status, "canonical_url": "https://example.com/index.html"}
            for n in range(to_home)
        ] + [{"url": f"https://www.example.com/o{n}", "status": 200, "canonical_url": f"https://www.example.com/o{n}"} for n in range(others)]

    assert spider.canonical_to_home(rows(3, 2)) == 3  # 3 of 6 pages
    assert spider.canonical_to_home(rows(2, 0)) == 0  # fewer than 3
    assert spider.canonical_to_home(rows(3, 4)) == 0  # under half of 8
    assert spider.canonical_to_home(rows(3, 0, status=404)) == 0  # error pages do not count
    offsite = [{"url": f"https://www.example.com/p{n}", "status": 200, "canonical_url": "https://other.example/"} for n in range(4)]
    assert spider.canonical_to_home(offsite) == 0  # another site's home page is not this one's
