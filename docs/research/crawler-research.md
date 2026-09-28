# Website Crawler - research for 1.2.0 (2026-09-28)

Scope: text, SEO audit, structured data, JS sites; owner priority = "downloads redundant data, not smart enough".
Method: primary docs, GitHub issues, PyPI JSON API [5], plus local experiments (marked LOCAL) on books.toscrape.com
and quotes.toscrape.com with trafilatura 2.2.0, readability-lxml 0.9, jusText 3.0.2, extruct 0.18.0, and a reading of the
installed Scrapy 2.19.0 / scrapy-playwright 0.0.48 source in .venv-win [50]. Reddit and Stack Overflow could not be
searched or fetched from this environment (the tool is blocked on both domains), so practitioner evidence comes from
GitHub issues and vendor engineering blogs instead. UNVERIFIED = could not confirm.

## 0. TOP PRIORITY - why the output is redundant and how to fix it

Where the current code creates redundancy (polite_crawler/spiders/site.py):
- Text = first //main|//article|role=main, else the whole page minus nav/header/footer tags only. Sidebars, cookie
  banners, "related products", breadcrumbs and div-based menus stay in every row; listing pages lose all but one article.
- page_key() = w3lib canonicalize_url: sorts query args, drops #fragment, fixes %-encoding, but does NOT normalise
  trailing slash, path case or www [27]. /a and /a/, ?sort=price variants and session ids all become separate rows.
- rel=canonical is stored but never used to dedupe; no content hash, so identical pages at different URLs are all kept.
- found_on keeps only the first referrer (the dupefilter drops later links), so broken-link reports are incomplete.

(1) Boilerplate repeated on every page
- trafilatura prunes nav/footer/aside and elements whose class/id match cookie, consent, newsletter, sidebar, related,
  relatedposts, then scores the rest by text and link density, with jusText as fallback [2][4] (LOCAL: xpaths.py).
- Benchmark on 990 docs (trafilatura's own eval, 2026-08): trafilatura F1 0.924, jusText 0.862, readability-lxml 0.826 [4];
  independent studies also rank it best single tool (Bevendorff et al. 2023, cited in [4]).
- LOCAL, word counts (listing page / product page / quotes page):
    trafilatura default 60 / 224 / 212; favor_recall 179 / 224 / 212; favor_precision 20 / 220 / 212
    readability-lxml 22 / 215 / 72;  jusText 0 / 193 / 0;  whole body minus nav/header/footer 301 / 227 / 269
  => article extractors (readability, jusText, trafilatura precision) throw away listing/category pages; use
     trafilatura favor_recall=True for page text. Readability and jusText are not good choices for a whole-site crawler.
- Site-wide block detection (text shared by most pages of a site = template) is the classic complement: Bar-Yossef &
  Rajagopalan 2002 [38]; boilerpipe's shallow text features (short, link-heavy blocks = boilerplate) [39]; Screaming Frog
  excludes nav/footer and lets users exclude more classes/ids for its content analysis [41].
- trafilatura has a built-in version: deduplicate=True drops any text segment >= 100 chars seen more than 2 times in the
  process (MIN_DUPLCHECK_SIZE=100, MAX_REPETITIONS=2), using an LRU cache; pass your own LRUCache per crawl, and
  reset_caches() between batches [3] (LOCAL settings.cfg). Caveats: order dependent (first 2 pages keep the block),
  ignores short menu lines (<100 chars), and can delete legitimately repeated text (disclaimers, specs).
- Recommended (own code, ~40 lines, no dependency): split each page's extracted text into blocks (lines/paragraphs),
  hash each normalised block (hashlib.blake2b, 8 bytes), count pages per block hash across the crawl; after the crawl
  (or after N>=20 pages) mark blocks present on >= 50% of pages (min 5 pages) as site boilerplate, write them once to
  boilerplate.json and strip them from text. Threshold is a design choice, tune on real sites (UNVERIFIED as a standard).

(2) Duplicate and near-duplicate pages
- Google lists the usual causes: http/https, www/non-www, trailing slash, sort/filter parameters, session ids, print
  versions, device/region variants [32]. Canonical signals by strength: redirects (strong), rel=canonical (strong but a
  hint), sitemap inclusion (weak) [32].
- URL normalisation rules to add before scheduling (all own code): lowercase scheme+host, drop default port, drop
  #fragment, remove tracking params (already done), remove session-id params (jsessionid, phpsessid, sid, sessionid,
  ;jsessionid= path params), sort query, treat /path and /path/ as one key (keep the first seen URL for fetching),
  collapse //, drop index.html/index.php in the key only. Zyte's duplicate-url-discarder (MIT) does the same with JSON
  rules (queryRemoval, queryRemovalExcept, subpathRemoval, normalizer) as a Scrapy fingerprinter/add-on [28]; good
  reference, but a dependency is not needed for this site-scoped crawler.
- Canonical handling: if a fetched page's canonical points to another in-scope URL, record canonical_of, enqueue the
  canonical target, and do not store full text for the non-canonical copy (keep the audit row only).
- Exact duplicates: Screaming Frog uses an MD5 of the full HTML [41]; for text use a hash of the cleaned main text
  (catches same content with different templates/ads). Store content_hash, and duplicate_of = first URL with that hash.
- Near duplicates: Screaming Frog = MinHash on page text, default 90% similarity, configurable content area [41];
  Google = 64-bit SimHash, Hamming distance k=3 at web scale (Manku et al. 2007) [37].
- LOCAL finding: trafilatura.deduplication.Simhash samples only ~64 long tokens [3]; listing pages 1, 2 and 3 of
  books.toscrape.com (different books) got IDENTICAL fingerprints (similarity 1.0), a false positive. A pure-Python
  64-bit SimHash over word 3-shingles (blake2b per shingle, ~15 lines) separated them (Hamming 23-25) and scored a
  lightly edited copy at 4. Recommend: shingle SimHash, candidate if Hamming <= 6, confirm with 3-shingle Jaccard >= 0.9
  (Screaming Frog's default) before setting near_duplicate_of. Skip pages under ~50 words.
- Libraries: datasketch MinHash (MIT) pulls numpy+scipy (~48 MB of wheels) and simhash (MIT, last release 2022) pulls
  numpy [5]; both are unnecessary for <= tens of thousands of pages.

(3) Crawl traps that multiply near-identical pages
- Google: faceted navigation creates "infinite URL spaces"; crawlers cannot know a URL is useless before fetching it [33][34].
- Heritrix defaults: PathologicalPathDecideRule rejects >2 identical consecutive path segments; TooManyPathSegments
  rejects >20 segments; TooManyHops >20 hops [35]; calendars are fenced with URL regexes [36].
- Automatic detection to add (own code): (a) per path-template budget - replace digits/ids with placeholders
  (/calendar/2026/09/28 -> /calendar/N/N/N) and cap URLs per template (e.g. 50); (b) per query-key budget - cap distinct
  values/combinations per parameter set, and never follow URLs with >2-3 filter params; (c) repeated segments and max
  path depth as in Heritrix; (d) date-like paths or ?date=/?month= beyond +-12 months of today; (e) pagination guard:
  stop a ?page=N series when a page's content_hash or shingle SimHash equals the previous page, or when N > 200;
  (f) template yield: if the last 20 pages of one template were all duplicates/near-duplicates, stop that template.
  Report each skip in audit.json as "trap_suspected" with the template and example URLs.

(4) What to store per page (compact, non-redundant)
- One row per URL for the audit (small fields), and main text only for unique, indexable, canonical 200 pages.
- Add: content_hash, simhash (16 hex chars), duplicate_of, near_duplicate_of, canonical_of, text_source
  ("trafilatura"|"fallback"), boilerplate removed once per site into boilerplate.json, not repeated per row.
- Keep full inlink lists out of results.jsonl; write edges once to links.csv (from, to, anchor, nofollow).

## A. Libraries per job (licence, size, Windows/PyInstaller, maintenance)

Sizes = LOCAL pip install --target, Linux, includes deps; lxml (~12 MB) is already in the app via Scrapy.
1. Main text
- trafilatura 2.2.0 (2026-07-31), Apache-2.0 since 1.8.0, py3-none-any, single maintainer, active (push 2026-09-25) [1][5].
  Deps: lxml, jusText, htmldate(+dateparser, regex, pytz), courlan(+babel, tld), charset_normalizer, urllib3 [5].
  Install size ~64 MB, of which babel 33 MB (32 MB locale data), dateparser+regex+pytz ~10 MB. PyInstaller: contrib hooks
  exist for dateparser, and core hook-babel collects ALL babel data [49]; trafilatura, justext (stoplists 2.5 MB) and tld
  need collect_data_files(). LOCAL: extract() still worked with babel/locale-data removed, so a trimmed build is
  plausible (UNVERIFIED in a frozen build).
- readability-lxml 0.9 (2026-08-27), Apache-2.0, ~25 KB + chardet, active [5][6]; article-only, fails on listings (LOCAL).
- jusText 3.0.2 (2025-02), BSD-2, 818 KB wheel [5][7]; same weakness.
- Pick: trafilatura (favor_recall=True, include_tables=True, include_comments=False, output_format="txt" or
  "markdown"), with the current XPath text as fallback when it returns < 30% of the fallback's words (listing pages).
2. SEO audit
- advertools 0.18.0 (2026-06), MIT, uses Scrapy, but depends on pandas + pyarrow (~37 MB of wheels) [5][10]. Use it as
  the reference for columns and redirect/link analysis (crawlytics.redirects(), links()) [11], not as a dependency.
- Pick: own code on Scrapy data (no new dependency).
3. Structured data
- extruct 0.18.0 (PyPI 2024-11-08; repo commits on 2026-09-27), BSD-3 [5][8]. Deps: rdflib, pyRdfa3, mf2py (+bs4,
  html5lib, requests), html-text, jstyleson, w3lib [5]. ~27 MB with lxml, so ~12-15 MB net. Import always loads rdflib
  (extruct/__init__ imports every extractor, LOCAL); contrib hook-rdflib exists [49]. uniform=True gives one shape for
  json-ld, microdata, opengraph, microformat, dublincore [8]. LOCAL: RDFa returned a triple on a page with no RDFa
  -> use syntaxes=["json-ld","microdata","opengraph"] by default.
- phonenumbers 9.0.40 (2026-09-24), Apache-2.0; full package ~46 MB installed (38 MB geodata); phonenumberslite
  ~5.4 MB without geocoder/carrier/timezone [5][9]. PhoneNumberMatcher finds numbers in free text [9]; contrib hook
  collects submodules [49].
- Emails: mailto: links + regex on visible text + JSON-LD email; no library needed (email-validator adds dnspython).
- Pick: extruct + phonenumberslite. Respect Cloudflare email obfuscation (data-cfemail / /cdn-cgi/l/email-protection)
  as the site's opt-out: record "email hidden by site", do not decode it [48].
4. JavaScript sites
- scrapy-playwright 0.0.48 (2026-07), BSD-3, active; only requests with meta playwright=True use the browser, others use
  the normal handler [12]. On Windows it runs Playwright in a ProactorEventLoop in a separate thread [12][13].
- Pick: keep scrapy-playwright; add auto-detect + per-request rendering (D).

## B. Pitfalls reported by practitioners

- Page cap: CLOSESPIDER_ITEMCOUNT/PAGECOUNT are soft; requests already in the downloader (up to CONCURRENT_REQUESTS)
  still finish [16]; issue #2748 (limit 1, several items) - advice is to enforce the count in your own code [21].
  Hard cap: count saved + in-flight page requests in the spider, stop yielding new page requests at the cap, drop items
  beyond it in the pipeline (DropItem), then raise CloseSpider("page_cap"); keep CLOSESPIDER_ITEMCOUNT as backstop.
- Duplicates: see 0(2). Also: redirected requests inherit dont_filter from the original, so a redirect to an already
  crawled URL is dropped by the dupefilter and never produces a row (LOCAL, redirect.py [50]); record redirects yourself.
- Traps: see 0(3); DEPTH_LIMIT alone does not stop wide traps (calendar months, facets) [33][35].
- robots.txt: RFC 9309 - 4xx means crawl allowed, 5xx means assume full disallow, cache <= 24 h, parse >= 500 KiB,
  follow >= 5 redirects; Crawl-delay is not in the standard [29]. Scrapy 2.18 added RobotParser.crawl_delay() [20][17]
  but RobotsTxtMiddleware still does not apply it (open request #5687 [23]; LOCAL: no use in 2.19 middleware). Apply
  it yourself: delay = max(user delay, crawl-delay), capped (e.g. 30 s), and tell the user.
- User agent: identify the bot with a stable name and a working contact URL or email [31]; the current UA is a
  placeholder. Set ROBOTSTXT_USER_AGENT to the bare token so robots.txt groups match [17].
- 429/Retry-After: Retry-After may be seconds or an HTTP date [30]. Scrapy's RetryMiddleware ignores it (issue #3849
  open; LOCAL: no reference in 2.19 code) [22]; AutoThrottle only lets non-200 latencies raise the delay, bounded by
  DOWNLOAD_DELAY..AUTOTHROTTLE_MAX_DELAY [18]. Add a middleware: on 429/503 read Retry-After, raise the slot delay to
  it, re-queue once or twice, and stop the crawl with a clear message if Retry-After > 10 min or 429s repeat.
- Memory: the MemoryUsage extension "does not work in Windows" [16]; main RAM growth in long crawls is the dupefilter
  fingerprint set [25] (2.18 stores them as bytes to save memory [20]). This spider also keeps saved_urls in RAM (fine
  at 1-10k pages). Playwright: users report large Chromium growth over hundreds of pages [26]; limit contexts/pages.
- JOBDIR: callbacks must be spider methods, one job per dir, resume only after a clean stop [19]; a hard kill can lose
  or corrupt the queue (issue #7978, opened 2026-08) [24]. server.py stops crawls with taskkill /F, so resume is
  unreliable. Scrapy handles SIGBREAK on Windows (LOCAL ossignal.py), and the worker already gets CREATE_NEW_PROCESS_GROUP:
  send CTRL_BREAK_EVENT first, wait ~20 s, then taskkill /F (UNVERIFIED with CREATE_NO_WINDOW; test it).
- Playwright in PyInstaller: official path is PLAYWRIGHT_BROWSERS_PATH=0 + bundle only the browsers you need [13]; the app
  downloading Chromium on first use keeps the zip small. Headless-only use can install with --only-shell (smaller than
  full Chromium, 281 MB on disk) [15]. networkidle is officially DISCOURAGED; wait for content instead [14].

## C. What a good SEO audit contains, and what fits a small polite crawler

Screaming Frog issue families [40]: response codes (4xx/5xx internal, no response, redirect chains/loops, blocked by
robots); URL (multiple slashes, spaces, uppercase, parameters, >115 chars); titles (missing, duplicate, multiple,
>60 or <30 chars, same as H1); meta description (missing, duplicate, multiple, >155 or <70 chars); H1 (missing,
multiple, duplicate, >70 chars); H2; content (exact duplicates, near duplicates, low content <200 words [42], soft 404);
images (missing alt, >100 KB); canonicals (missing, canonicalised, non-indexable canonical, multiple conflicting,
relative, outside head); directives (noindex, nofollow, outside head); links (no internal outlinks, nofollow-only inlinks,
high crawl depth, non-descriptive anchor text); structured data (parse errors, validation); sitemaps (non-indexable URLs
in sitemap, orphan URLs); pagination; hreflang. Redirect chain = redirect whose target redirects again ("hops") [43].
Sitebulb: slow TTFB hint fires above 600 ms [44]; orphan = URL found only via sitemap/other sources, not via crawler
links [45]. advertools columns: url, title, meta_desc, canonical, h1-h6, og:*, twitter:*, jsonld_*, body_text,
links_url/text/nofollow, nav/header/footer links, img_*, size, download_latency, status, depth, redirect_urls/
redirect_times/redirect_reasons, resp_headers_* [10].
Fits a small polite crawler (all from HTML already fetched, no extra requests): status + broken links with every source
page; redirect chains/loops; title/description missing/duplicate/length; H1 missing/multiple; canonical
missing/other/non-200/non-indexable target; noindex (meta robots + X-Robots-Tag) and "noindex in sitemap"; thin pages
(<200 words of main text); exact/near duplicates; slow responses (> 600 ms, and flag > 2 s); depth > 4; orphans (in
sitemap, zero internal inlinks); images missing alt; JSON-LD parse errors; mixed content (http resources on https).
Skip (cost or needs other data): pixel widths, spelling/grammar, semantic similarity, hreflang reciprocity, Core Web
Vitals, external link checking (optional HEAD requests later, off by default), GA/GSC orphan sources.

## D. Recommended design for this codebase

Concrete recommendation for the redundancy problem (do first, in 1.2.0):
1. Normalise URLs before scheduling (0(2) rules) and keep one key per page; honour in-scope rel=canonical.
2. Main text = trafilatura.extract(favor_recall=True, include_tables=True, include_comments=False); fallback to the
   current XPath over the whole body (not the first article) when trafilatura returns much less text.
3. Per page: content_hash (blake2b of normalised text) and shingle SimHash; set duplicate_of / near_duplicate_of; for
   duplicates, canonicalised and noindex pages store audit fields only (text = "").
4. Site-wide boilerplate: count block hashes across pages; at spider close write boilerplate.json and pages.jsonl
   (final clean text); keep results.jsonl streaming for the live dashboard.
5. Trap guard: per-template and per-parameter budgets, repeated segments, date windows, pagination-repeat stop;
   log each skip to audit.json.
6. Hard page cap in spider + pipeline (B).

New fields per result row (results.jsonl): final_url, redirect_chain [{url,status}], response_ms, content_type,
bytes, depth, source ("link"|"sitemap"|"seed"), indexable (bool) + indexability_reason, meta_robots, x_robots_tag,
canonical_url + canonical_status ("self"|"other"|"missing"), title_count, title_length, description_length,
h1 (list), h1_count, lang, word_count (main text), content_hash, simhash, duplicate_of, near_duplicate_of,
rendered_js (bool), render_reason, internal_links_out, external_links_out, images_missing_alt,
structured_types (e.g. ["Product","Organization"]), emails, phones. found_on stays (first referrer) for compatibility.
New output files (per job dir):
- links.csv: from_url, to_url, anchor_text, nofollow, internal - one line per link; gives every page a broken link is on,
  inlink counts, and orphans (sitemap URLs with 0 inlinks).
- audit.json: site summary + issue lists (id, severity, count, example URLs) built at spider close from results + links.
- structured.jsonl: one line per entity {url, syntax, type, data} from extruct (uniform=True).
- products.csv: url, name, sku, gtin, brand, price, currency, availability (schema.org suffix), rating, review_count
  from Product/Offer/AggregateOffer in JSON-LD @graph and microdata, fallback og:price/product:price meta.
- contacts.csv: url, type (email|phone), value (E.164 for phones), source (mailto|tel|jsonld|text).
- pages.jsonl (clean final text, only unique indexable pages) and boilerplate.json.
- CSV exports must keep the 1.1.2 formula-injection guard.
JavaScript reliability:
- Default = plain HTTP. Mark a page as a shell and re-request it once with meta playwright=True when: main text < 50
  words and (empty #root/#app/#__next, __NEXT_DATA__/__NUXT__/data-reactroot markers, noscript "enable JavaScript" text,
  or visible text < ~5% of HTML) [46]. Zyte found 40.6% of 11,100 landing pages needed JS by a "+50% meaningful HTML"
  test [47]. If a site's first ~5 pages are all shells, switch the rest of the crawl to rendering (and say so in the UI).
- Before rendering, try data already in the HTML: JSON-LD and __NEXT_DATA__ often carry the content [46].
- Waits: goto wait_until="domcontentloaded" or "load", then wait_for_selector("main, article, h1, #root > *") with a
  short timeout; avoid networkidle [14]. PLAYWRIGHT_ABORT_REQUEST: abort image, media, font (keep stylesheet/script) [12].
- Memory: PLAYWRIGHT_MAX_CONTEXTS=1, PLAYWRIGHT_MAX_PAGES_PER_CONTEXT=1-2, concurrency 1, keep
  playwright_include_page=False, PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER=True [12]; rotate the context every ~100
  rendered pages (own code, UNVERIFIED value); watch memory yourself (e.g. restart the browser) since MemoryUsage is off on
  Windows [16]. download_latency for rendered pages includes render time (LOCAL handler.py) - label response_ms as such.
- Politeness also applies to the browser's subrequests (CSS/JS), which bypass Scrapy's delay (UNVERIFIED how much).
Minimal new dependencies (requirements.txt + spec):
- trafilatura (~+50 MB installed, mostly babel locale data; try excluding babel/locale-data except root/en - test first).
- extruct (~+12-15 MB). Spec: collect_data_files for trafilatura, justext, tld; hidden imports for extruct/rdflib via
  contrib hooks; verify in the Windows CI build.
- phonenumberslite (~+5 MB). Do NOT use full phonenumbers (+46 MB).
- No numpy/scipy/pandas/pyarrow: avoid datasketch, simhash, advertools (each adds ~12-50 MB). Use hashlib for hashes.
Bloat summary: current dist/WebsiteCrawler = 180 MB, of which the Playwright driver is 103 MB (LOCAL). The three
libraries add roughly 70 MB untrimmed, or roughly 35 MB if babel locale data can be trimmed. Chromium stays a
first-run download.

## Sources
[1] https://pypi.org/project/trafilatura/  [2] https://trafilatura.readthedocs.io/en/latest/usage-python.html
[3] https://trafilatura.readthedocs.io/en/latest/deduplication.html  [4] https://trafilatura.readthedocs.io/en/latest/evaluation.html
[5] PyPI JSON API, e.g. https://pypi.org/pypi/extruct/json (versions, dates, licences, deps, wheel sizes; queried 2026-09-28)  [6] https://github.com/buriy/python-readability
[7] https://github.com/miso-belica/jusText  [8] https://github.com/scrapinghub/extruct
[9] https://github.com/daviddrysdale/python-phonenumbers  [10] https://advertools.readthedocs.io/en/master/advertools.spider.html
[11] https://advertools.readthedocs.io/en/master/advertools.crawlytics.html  [12] https://github.com/scrapy-plugins/scrapy-playwright
[13] https://playwright.dev/python/docs/library  [14] https://playwright.dev/python/docs/api/class-page
[15] https://playwright.dev/python/docs/browsers  [16] https://docs.scrapy.org/en/latest/topics/extensions.html
[17] https://docs.scrapy.org/en/latest/topics/downloader-middleware.html  [18] https://docs.scrapy.org/en/latest/topics/autothrottle.html
[19] https://docs.scrapy.org/en/latest/topics/jobs.html  [20] https://docs.scrapy.org/en/latest/news.html
[21] https://github.com/scrapy/scrapy/issues/2748  [22] https://github.com/scrapy/scrapy/issues/3849
[23] https://github.com/scrapy/scrapy/issues/5687  [24] https://github.com/scrapy/scrapy/issues/7978
[25] https://github.com/scrapy/scrapy/issues/5307  [26] https://github.com/scrapy-plugins/scrapy-playwright/issues/240
[27] https://w3lib.readthedocs.io/en/latest/w3lib.html  [28] https://github.com/zytedata/duplicate-url-discarder
[29] https://www.rfc-editor.org/rfc/rfc9309.html  [30] https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429
[31] https://docs.aws.amazon.com/prescriptive-guidance/latest/web-crawling-system-esg-data/best-practices.html  [32] https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
[33] https://developers.google.com/crawling/docs/faceted-navigation  [34] https://developers.google.com/search/blog/2024/12/crawling-december-faceted-nav
[35] https://heritrix.readthedocs.io/en/latest/bean-reference.html  [36] https://github.com/internetarchive/heritrix3/wiki/Avoiding-Too-Much-Dynamic-Content
[37] https://research.google/pubs/pub33026/  [38] https://research.google/pubs/template-detection-via-data-mining-and-its-applications/
[39] https://www.ccs.neu.edu/home/vip/teach/IRcourse/6_ML/other_notes/Boilerplate%20Detection%20using%20Shallow%20Text%20Features.pdf  [40] https://www.screamingfrog.co.uk/seo-spider/issues/
[41] https://www.screamingfrog.co.uk/seo-spider/tutorials/how-to-check-for-duplicate-content/  [42] https://www.screamingfrog.co.uk/seo-spider/issues/content/low-content-pages/
[43] https://www.screamingfrog.co.uk/seo-spider/issues/response-codes/internal-redirect-chain/  [44] https://sitebulb.com/hints/performance/reduce-server-response-times-ttfb/
[45] https://sitebulb.com/hints/links/url-is-orphaned-and-was-not-found-by-the-crawler/ (search snippet, page not fetched)  [46] https://dev.to/extractdata/how-to-tell-if-a-page-uses-javascript-rendering-and-what-to-do-about-it-5af8
[47] https://dev.to/extractdata/40-of-pages-are-empty-over-plain-http-lip  [48] https://developers.cloudflare.com/waf/tools/scrape-shield/email-address-obfuscation/
[49] https://github.com/pyinstaller/pyinstaller-hooks-contrib (stdhooks listing via GitHub API) and PyInstaller hook-babel.py  [50] LOCAL: .venv-win Scrapy 2.19.0 and scrapy-playwright 0.0.48 source; scratchpad experiments on books.toscrape.com
