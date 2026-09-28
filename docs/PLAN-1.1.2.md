# Plan: version 1.1.2, a smarter crawler and the safety fixes

Owner (2026-09-28): the crawler "downloads redundant data, it is not smart enough";
fix that and the four safety items; ship without the owner, reviewed by a
supervisor agent; he checks the release through "Check for Updates" on Windows.
Research: `docs/research/crawler-research.md` (50 sources, local tests).
The look of the dashboard does not change in this version (Slush redesign: 1.2.0).

## Verified problems (2026-09-28)

1. Page cap overshoot: 30 asked, 46 saved (`CLOSESPIDER_ITEMCOUNT` is soft).
2. Main text: the first `<main>`/`<article>` only; a books listing kept 11 words of ~301.
3. Redundancy: menus, footers and side blocks repeat in every page's text; URL
   variants (trailing slash, case, www, session ids) and `rel=canonical` twins are
   saved as separate pages; no content hash; no trap detection.
4. Dashboard: no Host, Origin or token checks (a simple cross-site POST reaches
   `/api/update/install` and `/api/jobs/{id}/stop`; DNS rebinding can read results).
5. Updates installed with no checksum or signature.
6. CSV export allows spreadsheet formulas (`=`, `+`, `-`, `@`, tab, CR at the start).
7. Placeholder contact in the user agent; Scrapy ignores `Retry-After` and
   robots.txt `Crawl-delay`; tests run only on tags.

## Build

A. Crawler (polite_crawler/, crawl.py, requirements):
- Main text with trafilatura (`favor_recall=True`, no comments, tables kept), falling
  back to the current XPath over the whole page when trafilatura returns less than
  half of it or fails. Keep `text` as main text only.
- Site-wide boilerplate pass in the pipeline at the end of the crawl: split text into
  blocks, hash them, remove blocks found on 50% or more of pages (minimum 5 pages),
  write them once to `boilerplate.json`; rewrite `results.jsonl` without them (keep
  the raw file as `results.raw.jsonl` only if cheap; otherwise not).
- URL normalisation before requests: lowercase scheme and host, remove default ports,
  one rule for trailing slash (strip except root), drop session ids (`jsessionid`,
  `phpsessid`, `sid`, `sessionid` params and `;jsessionid=` path parts) plus the
  existing tracking params, sort query keys. Follow an in-scope `rel=canonical` once
  and mark the page `canonical_of`.
- Duplicates: `content_hash` (sha256 of normalised main text) and `duplicate_of`
  (first URL with the same hash); near-duplicates with a small pure-Python SimHash
  over 3-word shingles plus a 90% overlap check, `near_duplicate_of`. No numpy.
- Traps: cap followed URLs per path pattern (digits replaced) and per query parameter
  name, reject repeated path segments and paths deeper than 12, calendar dates more
  than 12 months from today, and a pagination series that repeats the previous page's
  hash. Each skip is counted in `summary.json` under `skipped`.
- Hard page cap: count saved plus in-flight in the spider; stop scheduling at the cap;
  the pipeline drops items beyond the cap; raise CloseSpider; keep the setting as a
  backstop. A test: 30 asked means at most 30 saved.
- Politeness: honour `Retry-After` on 429/503 (small downloader middleware, capped at
  10 minutes, logged), apply robots.txt `Crawl-delay` as the minimum delay, and a real
  contact in the user agent: `WebsiteCrawler/<VERSION> (+https://github.com/addico786/website_crawler)`.
- Summary: pages saved, duplicates, near-duplicates, boilerplate blocks removed, traps
  skipped, so the owner can see it is smarter.

B. Dashboard safety (server.py, static/app.js):
- A per-launch secret token: the server creates it at start; the page gets it from a
  one-time link or a same-origin endpoint served only with a correct Host; every
  `/api/` request needs it in a header; reject wrong Host (only 127.0.0.1:<port> and
  localhost:<port>) and a foreign Origin; state-changing routes accept only JSON with
  the token. Keep the Windows window flow working (app.py opens the page).
- CSV: prefix cells starting with `= + - @`, tab or CR with a single quote.
- Update install: read the asset's `digest` (sha256) from the GitHub release API and
  refuse a download whose sha256 differs or when no digest is published; zip entries
  must stay inside the staging folder. Full signing needs the owner's key (later).
- CI: a GitHub Actions workflow on push and pull request that runs the tests on Linux
  (and the smoke test on Windows if cheap).

C. Release safety (.github/workflows/release.yml, WebsiteCrawler.spec):
- Bundle trafilatura's, justext's, lxml_html_clean's and courlan/tld data files in the
  spec (hidden imports and datas), check the size added (research: about 35-70 MB).
- Before publishing, the workflow runs the built `WebsiteCrawlerWorker.exe --crawl`
  against a local `python -m http.server` fixture site and fails if no page or no main
  text is saved. The release is published only after that passes.

## Tests
Existing smoke and e2e tests stay green; new tests for: listing page text; boilerplate
removal across pages; URL normalisation cases; canonical twins; exact and near
duplicates; each trap rule; the hard cap; Retry-After and Crawl-delay; the dashboard
token, Host and Origin checks; CSV formula escaping; the update digest check (a fake
release API and zip); a zip with `..` entries refused.

## Version and docs
VERSION 1.1.2 in server.py; README "What is new"; CONTEXT.md; a CHANGELOG.md is
created. Tag v1.1.2 only after CI and the Windows workflow's smoke crawl pass.

## Not in this version
The Slush redesign and orbs (1.2.0); the SEO audit report, structured data, contacts,
JavaScript shell detection (1.3.0); full update signing (owner key).

---

## Supervisor review (2026-09-28): required changes, binding

Verdict: ship with changes. Where these differ from the sections above, these win.
Baseline: the 14 existing tests pass.

Facts found in the code: app.py probes `/api/version` to detect a running app (a
401 would read as "port in use"); exports use `window.location.href` and logs use
`EventSource` (no headers possible); 1.1.1's updater takes the first `.zip` asset,
finds the exe by rglob, copies `_internal` (/MIR) and `*.exe`, honours
`CRAWLER_UPDATE_URL`; the server re-reads results.jsonl on every poll (so
`os.replace` over it fails on Windows); AutoThrottle's `mindelay` resets
`slot.delay` after each 200; DepthMiddleware drops silently; there are no PyInstaller
hooks for trafilatura, justext, courlan, htmldate or tld.

1. Dashboard guard (replaces the token idea). No token. One middleware on every
   request: 400 unless Host's hostname is 127.0.0.1 or localhost (or `HOST` if set);
   port not checked. For POST/PUT/PATCH/DELETE under /api/: 403 when Sec-Fetch-Site
   is present and not same-origin/none, when Origin is present and not
   http://<allowed host>:<port>, or when Content-Type is not application/json.
   app.js sends `Content-Type: application/json` and `{}` on stop, delete, install.
   GETs (results, export, SSE, /api/version) need only the Host check. index.html is
   served with `Cache-Control: no-store` and loads `/app.js?v=<VERSION>`. Tests use
   `TestClient(app, base_url="http://127.0.0.1:8000")`.
2. Boilerplate: never rewrite results.jsonl. It stays append-only; text is stored one
   block per `\n` line (trafilatura and fallback). At spider close read the whole file
   (resumes count), take blocks on >= 50% of pages with text (min 5 pages), write
   boilerplate.json via temp file + os.replace (retry on PermissionError). The server
   strips those blocks when reading, through one `load_items()` used by results,
   detail, export and overview, which also recomputes word_count. Missing or bad
   boilerplate.json means raw text. Shared code in `polite_crawler/textblocks.py`
   (no Scrapy import).
3. URL normalisation builds the dedupe key only. Requests go to the URL as found,
   minus tracking params and session ids (`jsessionid`, `phpsessid`, `sessionid`,
   `;jsessionid=`, and `sid` only when its value is 32 hex chars). Key: lowercase
   scheme and host, drop leading `www.`, default port, fragment; sort query; strip one
   trailing slash (not root); drop a final index.html/htm/php; keep path case. Skip a
   link whose key is already saved or requested. rel=canonical: if in scope with a
   different key, request it normally; the page keeps its text and links; no new field.
4. Conservative traps. Skip before requesting, counted in `skipped.<rule>`: the same
   segment 3+ times in a row or any segment more than 3 times; more than 20 segments;
   a date in the last path segments or in a date/month/year/day query value more than
   12 months in the future (past dates never skipped); `page`/`paged`/`pg` query
   values or /page/N above 500. Do not follow links from an exact duplicate.
   Per-template and per-parameter budgets are only reported (`suspected_traps` with
   template, count, 3 examples), not enforced.
5. Duplicates. `content_hash` only when word_count >= 50, else null. Near-duplicates:
   64-bit SimHash over 3-word shingles, Hamming distance <= 3, found through 4
   exact-match 16-bit bands; no all-pairs scan, no stored shingles, no Jaccard. Marker
   only. Spider init rebuilds saved keys, hashes, bands and row count from
   results.jsonl.
6. Hard cap = rows in the job's results.jsonl (earlier runs and 4xx/5xx rows count).
   The spider counts rows it yields from the existing count; at the cap it yields
   nothing more and raises CloseSpider('page_cap') after the row that reaches it; the
   pipeline drops rows beyond it. No in-flight counting. CLOSESPIDER_ITEMCOUNT stays
   as backstop. Test: 100-page fixture, cap 30, concurrency 8 -> exactly 30;
   render_js -> <= 30.
7. Updater contract: exactly one .zip asset, `WebsiteCrawler-windows.zip`, top folder
   with WebsiteCrawler.exe, WebsiteCrawlerWorker.exe, `_internal/` (all new files live
   in `_internal`). 1.1.2 picks the asset by name, hashes while downloading, compares
   with `digest` (strip `sha256:`). No digest -> /api/update/check returns
   `download_url: null` and the UI offers the release page. Before tagging, test the
   real path on Windows: unzip v1.1.1, run it with CRAWLER_UPDATE_URL pointing at a
   local JSON (tag v1.1.2, asset on a local http.server), POST /api/update/install,
   wait for /api/version to answer 1.1.2. The digest guards integrity, not
   authenticity; `extractall` already strips `..`.
8. Packaging: `trafilatura==2.2.0` pinned. Spec: collect_data_files for trafilatura,
   justext, courlan, htmldate, tld; copy_metadata for trafilatura, justext, courlan,
   htmldate, dateparser. No babel trimming. Call `extract(favor_recall=True,
   include_tables=True, include_comments=False, with_metadata=False,
   deduplicate=False, output_format='txt')` in try/except; fall back to XPath text when
   it fails or returns under 50% of the XPath words; skip it for bodies over 5 MB.
   Record the dist size in the PR.
9. Smoke before the tag: release.yml gets a build-and-smoke job on pull_request and
   tags, and a publish job (tags only, needs build). Frozen smoke:
   WebsiteCrawlerWorker.exe --crawl against tests/fixtures/site/ (a listing page, two
   pages sharing menu and footer, a page under 250 characters, a /a and /a/ pair);
   fail unless >= 4 rows, >= 1 `text_source == trafilatura`, boilerplate.json exists;
   and `WebsiteCrawler.exe --server-only` answers `/` and /api/version. Linux CI runs
   `python -m playwright install --with-deps chromium` before pytest.
10. Politeness: UA `WebsiteCrawler (+https://github.com/addico786/website_crawler)`,
    `ROBOTSTXT_USER_AGENT = "WebsiteCrawler"` (no version; the crawler must not import
    server.py). Always fetch robots.txt, even with --no-sitemap. Delay = max(user
    delay, Crawl-delay), capped 60 s, logged, set on the slot and on AutoThrottle's
    `mindelay`. Retry-After middleware at priority 560 (seconds or HTTP date), sets
    the slot delay, capped 600 s, logged.
11. Visible result: at close log `Result: N pages, D duplicates, ND near duplicates,
    B boilerplate blocks, T trap URLs skipped`; same numbers in summary.json. CSV gets
    `content_hash`, `duplicate_of`, `near_duplicate_of`, `text_source` (read with
    `.get()` for old rows). Formula escaping on every string cell.

Optional (later): graceful stop on Windows (1.1.3); cache load_items by (mtime,
size); babel trimming; near-duplicates may slip to 1.1.3 if time runs short.

## Build order (small commits)
1. Linux CI workflow; tests switched to base_url.
2. release.yml split, fixture site, frozen smoke (on current code first).
3. Host and write guard, app.js JSON bodies, no-store and `?v=`, tests.
4. CSV formula escaping, test.
5. Updater: asset by name, digest, zip check, tests.
6. User agent, Crawl-delay, Retry-After, tests.
7. Hard cap, test.
8. Key normalisation, session ids, canonical request, tests.
9. trafilatura pin, spec datas, main text and fallback (one block per line), tests;
   the Windows PR smoke must pass.
10. content_hash, no-follow from duplicates, banded near-duplicates, resume rebuild.
11. Conservative traps and suspected-trap report.
12. textblocks.py, boilerplate.json, server load_items.
13. Result log line and CSV columns.
14. VERSION 1.1.2, README, CHANGELOG, CONTEXT; the 1.1.1 -> 1.1.2 update test on
    Windows; merge; tag.
