# Plan: version 1.2.2, sites that answer every address with the same page

Owner report (2026-09-28): crawling https://textifydigitals.com saved /terms,
/privacy-policy, /services/... all with the home page's title, canonical, 681 words and
content hash 15361bb6..., each marked `duplicate_of` the home page. Same in earlier versions.

## Root cause (established from evidence, 2026-09-28)

1. The website: nginx answers every path, including made-up ones
   (/this-page-does-not-exist-xyz), with status 200 and the same 62,084-byte
   index.html (sha256 6aaf25ce...), a pre-rendered copy of the home page with
   `<link rel="canonical" href="/">` and the home page's title. The real page for a path
   only appears after the React app runs in a browser (React error #418, hydration
   mismatch, then a client render). Checked with curl (crawler and browser user agents)
   and inside Scrapy: requested URL = final URL, no redirects, byte-identical bodies.
2. The crawler, plain download: correct. Fresh request per URL (site.py `follow()` →
   `request()`), no URL rewritten to "/", HTTPCACHE_ENABLED = False, no shared state
   (every field comes from the callback's own `response`), canonical falls back to the
   page's own URL (not the home page), content_hash hashes the page's own text. It
   faithfully records identical responses, but it has no way to notice that it is being
   given the same page for every address, and says nothing.
3. The crawler, Render JavaScript: bug. `SiteSpider.request()` (site.py:131-132) sets
   `playwright: True` with no wait, so scrapy-playwright returns the page at the `load`
   event, sometimes mid-redraw. Measured on /terms: at domcontentloaded the home page
   (969 words, home title); in the crawler's own render path, a 72-word frame identical
   for /terms and /services/sms-api (so still duplicates); after the network goes quiet,
   the real page ("Terms of Service | Textify Digitals", 312 words).
4. The website, also: the app never updates `<link rel="canonical">`, so every page,
   even rendered, names the home page as canonical. That is a real SEO fault on the
   site (search engines may fold every page into the home page).

## Build

A. Render wait (done on this branch, commit 1): a `settle(page)` PageMethod waits for
   `networkidle` up to 10 s, then keeps what is shown; a timeout never fails the page.
   Result on textifydigitals.com with --render-js, 8 pages: 0 duplicates, each page's
   own title and text (105-554 words). Add a fixture test: a local server that answers
   every path with the same HTML whose script replaces the content after about 300 ms
   based on location.pathname; with render_js the rows differ, without it they match.

B. Diagnostics on every row (read with `.get()` so old rows still load):
   `requested_url` (first URL in the redirect chain, else request.url), `final_url`
   (response.url; `url` stays as today), `redirect_chain` (list, possibly empty),
   `response_bytes`, `response_sha256` (raw body; for rendered pages the rendered HTML,
   plus `rendered: true`). CSV gets the same columns.

C. Same-page detection, before any page is saved:
   - `start()` first requests a made-up path on the seed host,
     `/__websitecrawler_check_<8 random hex>` (dont_filter, no row, not counted
     toward the cap), then the seed. Record the check's status and response_sha256.
   - When the seed page (not rendered) is 200 and its response_sha256 equals the
     check's, the site answers every address with one page ("single-page app"):
     - log: `This site answers every address with the same page (a single-page app).`
       and write `summary.json` `site_notes: ["same_page_for_every_address"]`;
     - if rendering is available (Chromium installed; scrapy-playwright is already the
       download handler), switch the crawl to rendering: set `self.render_js = True`,
       re-request the seed rendered (dont_filter), and log `Switched to Render
       JavaScript.`; if the rendered seed fails (browser missing or crash), switch back,
       continue plain, and log `Render JavaScript is not available; pages will look the
       same. Install it from the dashboard.`
   - Independently, flag rows: `suspicious: "SAME_RESPONSE"` when a row's
     response_sha256 equals the made-up path's (or equals another saved row's with a
     different page key); counted in the Result line as `S suspicious`.
   - A made-up path answering 404 (normal sites) changes nothing.

D. Result line and dashboard: `Result: ... , S suspicious (same page for different
   addresses)`; when `same_page_for_every_address` is set and rendering was not used,
   the dashboard's job panel shows one line: "This site sends the same page for every
   address. Turn on Render JavaScript." (plain text, Slush styles, no new layout).

E. Canonical to home page: count rows (status 200, path not "/") whose canonical
   is the home page; if at least 3 such rows make up at least half of the saved pages,
   log `N pages name the home page as their canonical (a site problem)` and add
   `canonical_to_home` to `site_notes`. (The full audit comes in 1.3.0.)

F. Tests: the SPA fixture (plain: rows share response_sha256, `suspicious` set,
   `site_notes` set; auto-switch: rows differ), a normal fixture site (made-up path 404,
   nothing flagged, no switch), diagnostics fields present and correct across a redirect
   (fixture /old -> /new), the settle timeout (a page that polls forever still saves
   within the timeout), the frozen smoke unchanged, and one live check against
   textifydigitals.com with a cap of 8 (plain, no --render-js flag): auto-switch fires
   and saves 8 different pages.

G. Version 1.2.2, CHANGELOG, README, CONTEXT. PR, CI green (Linux and the Windows
   smoke), then merge and tag.

Not in 1.2.2: the full SEO audit and `render=auto` for empty shells (1.3.0 / 1.3.1).
Note for 1.3.1: the planned shell trigger (under 50 words) would not catch this site,
whose fallback page has 681 words; the same-page check in C is the trigger that does.
