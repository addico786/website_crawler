import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit

import scrapy
from scrapy.exceptions import CloseSpider
from scrapy.http import HtmlResponse
from scrapy.linkextractors import IGNORED_EXTENSIONS, LinkExtractor
from scrapy.utils.gz import gunzip
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from scrapy.utils.url import url_has_any_extension
from scrapy_playwright.page import PageMethod
from playwright.async_api import TimeoutError as PlaywrightTimeout
from w3lib.url import canonicalize_url

from polite_crawler.fingerprints import NearDuplicates, content_hash, simhash
from polite_crawler.maintext import main_text
from polite_crawler.pipelines import read_summary, update_summary
from polite_crawler.traps import TrapGuard

# Files, not pages. Scrapy's list plus a few it misses.
DENY_EXTENSIONS = sorted(set(IGNORED_EXTENSIONS) | {"avif", "gz", "json", "woff", "woff2"})
# Click-tracking tags: the same page with a different label, not a new page.
TRACKING_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
)


# Session ids: the same page for every visitor. "sid" only when it looks like one (32 hex digits).
SESSION_PARAMS = ("jsessionid", "phpsessid", "sessionid")
SESSION_ID = re.compile(r"[0-9a-f]{32}", re.I)
DEFAULT_PORTS = {"http": 80, "https": 443}
INDEX_FILE = re.compile(r"/index\.(?:html?|php)$", re.I)
# summary.json site_notes: the site sends the start page's bytes for an address that cannot exist.
SAME_PAGE = "same_page_for_every_address"


async def settle(page):
    """Wait until the page stops loading data (at most 10 s), so the HTML we save is what
    the page shows. Apps that route in the browser redraw after the load event: without
    this, /terms can be saved mid-redraw, still carrying the home page's HTML or a bare frame."""
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass  # a page that polls forever: keep what it shows now


def clean_url(url):
    """The URL to request: as found, minus click-tracking tags and session ids."""
    parts = urlsplit(url)
    path = re.sub(r";jsessionid=[^/?#]*", "", parts.path, flags=re.I)
    kept = []
    for pair in parts.query.split("&") if parts.query else []:
        name, _, value = pair.partition("=")
        name = unquote(name).lower()
        if name in TRACKING_PARAMS or name in SESSION_PARAMS or (name == "sid" and SESSION_ID.fullmatch(unquote(value))):
            continue
        kept.append(pair)
    return urlunsplit(parts._replace(path=path, query="&".join(kept)))


def page_key(url):
    """Same page => same key. Used only to spot duplicates; requests go to the URL as found.

    Ignores host case, a leading www., the default port, #fragments, query order, one trailing
    slash and a final index.html/htm/php. Keeps path case (servers may treat /A and /a apart).
    """
    parts = urlsplit(canonicalize_url(clean_url(url)))
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    if parts.port and parts.port != DEFAULT_PORTS.get(parts.scheme):
        host += f":{parts.port}"
    path = INDEX_FILE.sub("/", parts.path) or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


class SiteSpider(scrapy.Spider):
    name = "site"

    def __init__(self, start_url=None, job_dir=None, use_sitemap="True", render_js="False", max_pages="0", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not start_url or not job_dir:
            raise ValueError("Pass -a start_url=https://example.com")
        parsed = urlparse(start_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("start_url must be an http(s) URL")
        self.start_urls = [start_url]
        self.hosts = set()
        self.add_host(parsed.hostname)
        # Informational only: scope is enforced by in_scope(), since Scrapy's
        # allowed_domains admits every subdomain and can't follow a seed redirect.
        self.allowed_domains = sorted(self.hosts)
        self.job_dir = job_dir
        self.use_sitemap = str(use_sitemap).lower() == "true"
        self.render_js = str(render_js).lower() in ("true", "1", "yes")
        # Hard cap on rows in results.jsonl, earlier runs of this job and error pages included
        # (CLOSESPIDER_ITEMCOUNT only stops after the requests already in flight). 0 means no cap.
        self.max_pages = int(max_pages or 0)
        # Pages saved by earlier runs of this job, so resuming doesn't save them twice.
        results = Path(job_dir) / "results.jsonl"
        self.saved_urls = set()
        self.rows = 0
        # Text fingerprints of saved pages: content_hash -> first URL, and the SimHash bands.
        self.hashes = {}
        self.near_duplicates = NearDuplicates()
        # Bodies of saved pages: response_sha256 -> page key of the first page sent with those bytes.
        self.responses = {}
        if results.exists():
            with results.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        self.saved_urls.add(page_key(row["url"]))
                        self.rows += 1
                        self.remember_text(row)
                        self.remember_response(row)
        # Keys of pages saved or already requested: a link to one of them is not requested again.
        self.seen_keys = set(self.saved_urls)
        self.traps = TrapGuard()
        self.link_extractor = LinkExtractor(deny_extensions=DENY_EXTENSIONS, process_value=clean_url, unique=True)
        # What a made-up address returned (see check_site()) and what the crawl decided from it. Kept in
        # summary.json, so a resumed job neither checks again nor forgets that it switched to rendering.
        earlier = read_summary(job_dir)
        self.site_check = earlier.get("same_page_check")
        self.site_notes = [note for note in earlier.get("site_notes", []) if note == SAME_PAGE]
        self.render_js_switched = bool(earlier.get("render_js_switched"))
        self.render_js = self.render_js or self.render_js_switched
        self.render_failed = False
        # Sitemap pages wait until the start page has decided whether the crawl renders.
        self.seed_done = False
        self.waiting = []

    def remember_text(self, row):
        """Record a saved page's fingerprints so later copies are marked as duplicates."""
        if row.get("content_hash") and not row.get("duplicate_of"):
            self.hashes.setdefault(row["content_hash"], row["url"])
            if row.get("simhash"):
                self.near_duplicates.add(int(row["simhash"], 16), row["url"])

    def remember_response(self, row):
        if row.get("status", 0) < 300 and row.get("response_sha256"):
            self.responses.setdefault(row["response_sha256"], page_key(row["url"]))

    def fallback_sha256(self):
        """sha256 of the page the site sent, with 200, for the made-up address; None for a normal 404."""
        check = self.site_check
        if check and check.get("status") == 200 and urlsplit(check["final_url"]).path == urlsplit(check["url"]).path:
            return check["response_sha256"]
        return None

    def same_response(self, row):
        """SAME_RESPONSE when a page arrived with the bytes sent for the made-up address, or with
        those of another saved page: one page sent for different addresses."""
        sha = row.get("response_sha256")
        if row["status"] >= 300 or not sha:
            return None
        if sha == self.fallback_sha256() or self.responses.get(sha, page_key(row["url"])) != page_key(row["url"]):
            return "SAME_RESPONSE"
        return None

    def site_state(self):
        return {
            "same_page_check": self.site_check,
            "site_notes": list(self.site_notes),
            "render_js": self.render_js,
            "render_js_switched": self.render_js_switched,
        }

    def save_site_state(self):
        # Now, not only at the end: stopping a job from the dashboard kills the crawl.
        update_summary(self.job_dir, self.site_state())

    def add_host(self, host):
        host = host.lower()
        base_host = host[4:] if host.startswith("www.") else host
        self.hosts |= {base_host, f"www.{base_host}"}

    def in_scope(self, url):
        return (urlparse(url).hostname or "").lower() in self.hosts

    def is_page_url(self, url):
        return self.in_scope(url) and not url_has_any_extension(url, ["." + ext for ext in DENY_EXTENSIONS])

    def request(self, url, callback=None, dont_filter=False, errback=None, **meta):
        # allow_offsite: in_scope() already decided; Scrapy's offsite filter would
        # otherwise drop hosts adopted after a seed redirect.
        meta = {"allow_offsite": True, **meta}
        if self.render_js and callback is None:
            meta |= {"playwright": True, "playwright_include_page": False, "playwright_page_methods": [PageMethod(settle)]}
        return scrapy.Request(url, callback=callback or self.parse, errback=errback, meta=meta, dont_filter=dont_filter)

    def seed_request(self):
        return self.request(self.start_urls[0], dont_filter=True, errback=self.seed_failed, seed=True)

    def follow(self, url):
        """Request a page unless a URL with the same key was already requested or saved, or it is a trap."""
        key = page_key(url)
        if key not in self.seen_keys:
            self.seen_keys.add(key)
            if self.traps.allow(url):
                yield self.request(url)

    async def check_site(self, seed):
        """Ask for an address that cannot exist, before any page. A normal site answers 404. A site
        that answers 200 with the start page's bytes sends one page for every address (see parse()).
        Downloaded directly, not scheduled: no row, no page count, no links, never a broken link."""
        parts = urlsplit(seed)
        url = f"{parts.scheme}://{parts.netloc}/__websitecrawler_check_{secrets.token_hex(4)}"
        request = scrapy.Request(url, dont_filter=True, meta={"allow_offsite": True})
        try:
            response = await self.crawler.engine.download_async(request)
        except Exception as error:  # unreachable, or robots.txt disallows it: crawl as before
            self.logger.info("Could not check a made-up address (%s): %s", url, error)
            return None
        self.logger.info("A made-up address (%s) answered %s.", url, response.status)
        return {
            "url": url,
            "status": response.status,
            "final_url": response.url,
            "response_sha256": hashlib.sha256(response.body).hexdigest(),
        }

    async def start(self):
        seed = self.start_urls[0]
        self.seen_keys.add(page_key(seed))
        if self.site_check is None:
            self.site_check = await self.check_site(seed)
            if self.site_check:
                self.save_site_state()
        yield self.seed_request()
        if self.use_sitemap:
            parsed = urlparse(seed)
            yield self.request(f"{parsed.scheme}://{parsed.netloc}/robots.txt", callback=self.parse_robots, dont_filter=True)

    def parse_robots(self, response):
        # Sites often keep the sitemap elsewhere (sitemap_index.xml, wp-sitemap.xml) and say so in robots.txt.
        found = list(sitemap_urls_from_robots(response.body, base_url=response.url)) if response.status == 200 else []
        for url in found or [response.urljoin("/sitemap.xml")]:
            if self.in_scope(url):
                yield self.request(url, callback=self.parse_sitemap)

    def parse_sitemap(self, response):
        if response.status != 200:
            return
        body = response.body
        if body[:2] == b"\x1f\x8b":  # sitemap.xml.gz
            body = gunzip(body, max_size=50 * 1024 * 1024)
        sitemap = Sitemap(body)
        if sitemap.type not in ("urlset", "sitemapindex"):
            return
        # Sitemap yields only <url>/<sitemap> locations, not <image:loc> and friends.
        for entry in sitemap:
            url = clean_url(response.urljoin(entry["loc"].strip()))
            if sitemap.type == "sitemapindex":
                if self.in_scope(url):
                    yield self.request(url, callback=self.parse_sitemap)
            elif self.is_page_url(url):
                if self.seed_done:
                    yield from self.follow(url)
                else:  # a plain request now would miss a switch to rendering
                    self.waiting.append(url)

    def start_page_decided(self):
        """The start page is in, rendered or not: request the sitemap pages that waited for it."""
        self.seed_done = True
        waiting, self.waiting = self.waiting, []
        for url in waiting:
            yield from self.follow(url)

    def seed_failed(self, failure):
        if failure.request.meta.get("playwright") and self.render_js_switched:
            # Chromium is missing or crashed: crawl without it, as before the switch.
            self.render_js = self.render_js_switched = False
            self.render_failed = True
            self.logger.warning("Render JavaScript is not available; pages will look the same. Install it from the dashboard.")
            self.logger.info("Rendering the start page failed: %s", failure.value)
            self.save_site_state()
            self.crawler.engine.crawl(self.seed_request())
            return
        self.logger.error("Could not download the start page %s: %s", failure.request.url, failure.value)
        yield from self.start_page_decided()

    def switch_to_rendering(self, response):
        """True when the start page came back as the made-up address's page and the crawl now renders.
        Its HTML is then the same for every address; only a browser shows the real pages."""
        if response.meta.get("playwright") or response.status != 200:
            return False
        if self.fallback_sha256() != hashlib.sha256(response.body).hexdigest():
            return False
        if SAME_PAGE not in self.site_notes:
            self.site_notes.append(SAME_PAGE)
            self.logger.warning("This site answers every address with the same page (a single-page app).")
        if not self.render_failed:  # this run already found that rendering does not work
            self.render_js = self.render_js_switched = True
            self.logger.info("Switched to Render JavaScript.")
        self.save_site_state()
        return self.render_js_switched

    def at_cap(self):
        return bool(self.max_pages) and self.rows >= self.max_pages

    def parse(self, response):
        if self.at_cap():  # a response still in flight, or a resumed job already at its cap
            raise CloseSpider("page_cap")
        if response.meta.get("seed"):
            if not self.in_scope(response.url):
                # e.g. example.com -> example.co.uk: crawl where the site actually lives.
                self.logger.info("Start URL redirected to %s; crawling that site instead.", response.url)
                self.add_host(urlparse(response.url).hostname)
            if self.switch_to_rendering(response):
                # Not yielded: a request from this callback would count one level deeper.
                self.crawler.engine.crawl(self.seed_request())
                return
            yield from self.start_page_decided()
        key = page_key(response.url)
        if key in self.saved_urls or not self.in_scope(response.url):
            return
        self.saved_urls.add(key)
        self.seen_keys.add(key)
        found_on = response.request.headers.get("Referer", b"").decode("latin-1")

        if not isinstance(response, HtmlResponse):
            # PDFs, images etc. served without a telltale extension: not pages. Broken ones still get a row.
            if response.status >= 400:
                yield self.item(response, found_on)
                if self.at_cap():
                    raise CloseSpider("page_cap")
            return

        clean_text, text_source = main_text(response.text, response.selector.root)
        # Error pages often share one text ("Not found"); they are not duplicates of each other.
        text_hash = content_hash(clean_text) if response.status < 300 else None
        fingerprint = simhash(clean_text) if text_hash else None
        duplicate_of = self.hashes.get(text_hash)
        near_duplicate_of = self.near_duplicates.find(fingerprint) if fingerprint is not None and not duplicate_of else None
        robots_meta = " ".join(response.xpath("//meta[@name='robots']/@content").getall()).lower()
        canonical_url = response.urljoin(response.css("link[rel='canonical']::attr(href)").get(default=response.url))
        links = [
            link for link in self.link_extractor.extract_links(response)
            if self.in_scope(link.url) and not link.nofollow
        ]
        item = self.item(
            response,
            found_on,
            title=response.css("title::text").get(default="").strip(),
            description=response.css("meta[name='description']::attr(content)").get(default="").strip(),
            canonical_url=canonical_url,
            headings=[heading.strip() for heading in response.css("h1::text, h2::text").getall() if heading.strip()],
            text=clean_text,
            text_source=text_source,
            word_count=len(clean_text.split()),
            links_found=len(links),
            content_hash=text_hash,
            simhash=f"{fingerprint:016x}" if fingerprint is not None else None,
            duplicate_of=duplicate_of,
            near_duplicate_of=near_duplicate_of,
        )
        self.remember_text(item)
        yield item
        if self.at_cap():
            raise CloseSpider("page_cap")
        # Error pages' relative links resolve against a URL that doesn't exist, which
        # spirals into /missing/deeper/deeper/... Only follow links from real pages.
        # An exact copy of a saved page links to the same places (and may be a trap: a
        # pagination series past its end repeats the last page).
        if response.status < 300 and "nofollow" not in robots_meta and not duplicate_of:
            # The page names another URL as the real one (e.g. ?color=red -> the product): fetch that too.
            if page_key(canonical_url) != key and self.is_page_url(canonical_url):
                yield from self.follow(clean_url(canonical_url))
            for link in links:
                yield from self.follow(link.url)

    def item(self, response, found_on, **fields):
        self.rows += 1
        # What the server sent, to tell apart pages that only look alike from one page sent for many
        # addresses. A rendered page's body is the HTML the browser ended up with.
        redirects = response.request.meta.get("redirect_urls", []) if response.request else []
        row = {
            "url": response.url,
            "status": response.status,
            "title": "",
            "description": "",
            "canonical_url": response.url,
            "headings": [],
            "text": "",
            "text_source": None,
            "word_count": 0,
            "links_found": 0,
            "content_hash": None,
            "simhash": None,
            "duplicate_of": None,
            "near_duplicate_of": None,
            "suspicious": None,
            **fields,
            "requested_url": redirects[0] if redirects else (response.request.url if response.request else response.url),
            "final_url": response.url,
            "redirect_chain": list(redirects),
            "response_bytes": len(response.body),
            "response_sha256": hashlib.sha256(response.body).hexdigest(),
            "rendered": bool(response.request and response.request.meta.get("playwright")),
            "found_on": found_on,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        row["suspicious"] = self.same_response(row)
        self.remember_response(row)
        return row
