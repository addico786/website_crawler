# Changelog

## 1.2.2 (2026-09-28)

Sites that send the same page for every address (`docs/PLAN-1.2.2.md`). textifydigitals.com's
server answers every path, even a made-up one, with status 200 and the same pre-rendered home
page; the real page only appears once the site's JavaScript runs. Every page was saved as a copy
of the home page.

Crawler
- Render JavaScript waits until the page stops loading data (at most 10 s) before saving it, so an
  app that draws the page after the load event is no longer saved mid-redraw.
- Before the first page, the crawl asks for a made-up address (`/__websitecrawler_check_<8 hex>`):
  no row, not counted toward the page cap, never followed or reported as a broken link. When the
  start page comes back 200 with exactly the same bytes, the log says "This site answers every
  address with the same page (a single-page app).", `summary.json` gets `site_notes:
  ["same_page_for_every_address"]`, and the crawl switches to Render JavaScript on its own. If the
  browser is missing, it goes on without it and says pages will look the same. A resumed job keeps
  the check and the decision (both in `summary.json`).
- Rows whose bytes are the made-up address's, or another saved page's, are marked
  `suspicious: "SAME_RESPONSE"`; the Result line ends with `S suspicious (same page for different
  addresses)`.
- When at least 3 pages, and at least half of them, name the home page as their canonical, the log
  says so (a fault of the site) and `site_notes` gets `canonical_to_home`.
- Every row records what was asked for and what came back: `requested_url`, `final_url`,
  `redirect_chain`, `response_bytes`, `response_sha256` (for a rendered page, of the rendered HTML)
  and `rendered`. The CSV export has the same columns.

Dashboard
- A job that found one page for every address and did not render shows: "This site sends the same
  page for every address. Turn on Render JavaScript."

Windows app
- A real installer, `WebsiteCrawler-Setup.exe` (Inno Setup): per user, no admin prompt, into
  `%LOCALAPPDATA%\Programs\WebsiteCrawler`; Start-menu and desktop shortcuts; an uninstaller in Apps
  & features that asks before deleting crawl results. The release notes open with which file to
  download. `WebsiteCrawler-windows.zip` is unchanged and is still what "Check for Updates" installs.
- The pull-request build installs the app silently, starts it and uninstalls it.

## 1.2.1 (2026-09-28)

The crawler fixes planned as 1.1.2 (`docs/PLAN-1.1.2.md`), on top of the 1.2.0 redesign.

Crawler: less redundant data
- Main text with trafilatura, so a listing page keeps all its items (books.toscrape.com's
  listing: 11 words before). Falls back to the page's own text when trafilatura fails or keeps
  under half of it. Each row says which in `text_source`.
- Site-wide boilerplate: text blocks found on at least half of a job's pages (and on at least 5)
  are written once to `boilerplate.json` and left out of the dashboard, the exports and the word
  counts. `results.jsonl` still holds the full text.
- One request per page: URL variants (trailing slash, `www.`, default port, `index.html`, query
  order, session ids) count as one page; an in-scope `rel=canonical` is requested once.
- Exact duplicates (`content_hash`, `duplicate_of`) and near-duplicates (`near_duplicate_of`)
  are marked; links on an exact copy are not followed.
- Clear crawler traps (endless calendars, `/a/a/a/...` loops, very deep pagination) are skipped
  before any request; large URL families are listed in `summary.json` as `suspected_traps`.
- Hard page cap: a cap of 30 saves exactly 30 rows (it saved 46).
- The job log ends with `Result: N pages, D duplicates, ND near duplicates, B boilerplate
  blocks, T trap URLs skipped`; `summary.json` has the same numbers under `result`.
- CSV export: new columns `text_source`, `content_hash`, `duplicate_of`, `near_duplicate_of`.

Politeness
- A real user agent: `WebsiteCrawler (+https://github.com/addico786/website_crawler)`.
- robots.txt `Crawl-delay` is honoured (up to 60 s) and `Retry-After` on 429/503 (up to 10 min).

Safety
- The dashboard refuses unknown Host names (DNS rebinding) and cross-site writes: stop, delete,
  start and install need a same-site JSON request.
- The updater installs only `WebsiteCrawler-windows.zip`, and only when its sha256 matches the
  digest GitHub publishes for the release asset; without a digest it offers the release page.
- CSV cells that would run as spreadsheet formulas (`= + - @`, tab, CR) are escaped.
- The dashboard page is not cached, and loads `app.js`, `app.css` and `orbs.js` with
  `?v=<version>`, so an update never runs old scripts.

Build and tests
- Tests run on Linux for every pull request and push to main; every pull request also builds the
  Windows app and smoke-tests the built exe (a crawl of a fixture site and the dashboard). A tag is
  published only after that passes.

## 1.2.0 (2026-09-28)

- The Slush redesign of the dashboard, with thinking-orbs loaders (fonts and the orbs engine are
  bundled; nothing loads from the internet).
