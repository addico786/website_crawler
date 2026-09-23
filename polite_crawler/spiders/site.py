import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import scrapy
from scrapy.http import HtmlResponse
from scrapy.linkextractors import IGNORED_EXTENSIONS, LinkExtractor
from scrapy.utils.gz import gunzip
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from scrapy.utils.url import url_has_any_extension
from w3lib.url import canonicalize_url, url_query_cleaner

# Files, not pages. Scrapy's list plus a few it misses.
DENY_EXTENSIONS = sorted(set(IGNORED_EXTENSIONS) | {"avif", "gz", "json", "woff", "woff2"})
# Click-tracking tags: the same page with a different label, not a new page.
TRACKING_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
)


def strip_tracking(url):
    return url_query_cleaner(url, TRACKING_PARAMS, remove=True, unique=False, keep_fragments=True)


def page_key(url):
    """Same page => same key: ignores #fragments, query order and trailing-slash-on-host."""
    return canonicalize_url(url)


class SiteSpider(scrapy.Spider):
    name = "site"

    def __init__(self, start_url=None, job_dir=None, use_sitemap="True", render_js="False", *args, **kwargs):
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
        # Pages saved by earlier runs of this job, so resuming doesn't save them twice.
        results = Path(job_dir) / "results.jsonl"
        self.saved_urls = set()
        if results.exists():
            with results.open(encoding="utf-8") as f:
                self.saved_urls = {page_key(json.loads(line)["url"]) for line in f if line.strip()}
        self.link_extractor = LinkExtractor(deny_extensions=DENY_EXTENSIONS, process_value=strip_tracking, unique=True)

    def add_host(self, host):
        host = host.lower()
        base_host = host[4:] if host.startswith("www.") else host
        self.hosts |= {base_host, f"www.{base_host}"}

    def in_scope(self, url):
        return (urlparse(url).hostname or "").lower() in self.hosts

    def is_page_url(self, url):
        return self.in_scope(url) and not url_has_any_extension(url, ["." + ext for ext in DENY_EXTENSIONS])

    def request(self, url, callback=None, dont_filter=False, **meta):
        # allow_offsite: in_scope() already decided; Scrapy's offsite filter would
        # otherwise drop hosts adopted after a seed redirect.
        meta = {"allow_offsite": True, **meta}
        if self.render_js and callback is None:
            meta |= {"playwright": True, "playwright_include_page": False}
        return scrapy.Request(url, callback=callback or self.parse, meta=meta, dont_filter=dont_filter)

    async def start(self):
        seed = self.start_urls[0]
        yield self.request(seed, dont_filter=True, seed=True)
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
            url = strip_tracking(response.urljoin(entry["loc"].strip()))
            if sitemap.type == "sitemapindex":
                if self.in_scope(url):
                    yield self.request(url, callback=self.parse_sitemap)
            elif self.is_page_url(url):
                yield self.request(url)

    def parse(self, response):
        if response.meta.get("seed") and not self.in_scope(response.url):
            # e.g. example.com -> example.co.uk: crawl where the site actually lives.
            self.logger.info("Start URL redirected to %s; crawling that site instead.", response.url)
            self.add_host(urlparse(response.url).hostname)
        key = page_key(response.url)
        if key in self.saved_urls or not self.in_scope(response.url):
            return
        self.saved_urls.add(key)
        found_on = response.request.headers.get("Referer", b"").decode("latin-1")

        if not isinstance(response, HtmlResponse):
            # PDFs, images etc. served without a telltale extension: not pages. Broken ones still get a row.
            if response.status >= 400:
                yield self.item(response, found_on)
            return

        content = response.xpath("//main | //article | //*[@role='main']")
        root = content[0] if content else response
        text = root.xpath(
            ".//text()[normalize-space() and not(ancestor::script | ancestor::style | ancestor::noscript | ancestor::svg | ancestor::nav | ancestor::footer | ancestor::header)]"
        ).getall()
        clean_text = " ".join(part.strip() for part in text if part.strip())
        robots_meta = " ".join(response.xpath("//meta[@name='robots']/@content").getall()).lower()
        links = [
            link for link in self.link_extractor.extract_links(response)
            if self.in_scope(link.url) and not link.nofollow
        ]
        yield self.item(
            response,
            found_on,
            title=response.css("title::text").get(default="").strip(),
            description=response.css("meta[name='description']::attr(content)").get(default="").strip(),
            canonical_url=response.urljoin(response.css("link[rel='canonical']::attr(href)").get(default=response.url)),
            headings=[heading.strip() for heading in response.css("h1::text, h2::text").getall() if heading.strip()],
            text=clean_text,
            word_count=len(clean_text.split()),
            links_found=len(links),
        )
        # Error pages' relative links resolve against a URL that doesn't exist, which
        # spirals into /missing/deeper/deeper/... Only follow links from real pages.
        if response.status < 300 and "nofollow" not in robots_meta:
            for link in links:
                yield self.request(link.url)

    def item(self, response, found_on, **fields):
        return {
            "url": response.url,
            "status": response.status,
            "title": "",
            "description": "",
            "canonical_url": response.url,
            "headings": [],
            "text": "",
            "word_count": 0,
            "links_found": 0,
            **fields,
            "found_on": found_on,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
