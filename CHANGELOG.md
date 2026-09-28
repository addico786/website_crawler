# Changelog

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
