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
