# Context - Website Crawler

- Owner: addico786. Client project. Public repo; releases (tag `v*`) are
  built on Windows by `.github/workflows/release.yml` and reach users
  through the app's "Check for Updates".
- Owner's request (2026-09-28): fix what is broken and make the crawler do
  its job, then redesign it like Switchyard with orb loaders (design system
  to come from the owner). Ship one or two versions without the owner,
  each reviewed by a supervisor agent. Budget-conscious: one agent at a
  time, Opus 5.5 only, never the ponytail skills.
- Its job (owner): full text of every page; a site health / SEO audit;
  structured data (products, contacts, JSON-LD); reliable JavaScript sites.
- Findings (2026-09-28, verified): a real 30-page crawl of
  books.toscrape.com saved 46 pages (CLOSESPIDER_ITEMCOUNT is a soft stop);
  listing pages keep only the first `<article>` (11 words for 20 books);
  the dashboard has no Host/Origin/token checks (any web page can POST to
  it; DNS rebinding can read it); updates are installed without any
  checksum or signature; CSV export allows spreadsheet formulas; the
  crawler's contact address is a placeholder; tests run only on tags.
  All 14 tests pass (`env/bin/python -m pytest test_smoke.py test_e2e.py`).
- Owner (2026-09-28): the redesign uses the "Slush" design system
  (`docs/design-system-slush.md`, adaptation rules bind) with thinking-orbs
  loaders; the owner checks each release through the app's "Check for
  Updates" on Windows. thinking-orbs ships a React-free engine
  (`thinking-orbs/engine`, about 27 KB, MIT) usable from the plain-JS page.
  The owner's complaint: "downloading redundant data, not smart enough"
  (boilerplate, duplicate pages, traps).
- Plan: 1.1.2 = fixes (page cap, full text of listing pages, dashboard
  protection, CSV safety, update checksum from GitHub's asset digest,
  real contact address, CI on push and pull requests); 1.2.0 = the Slush redesign with orbs; 1.3.0 = SEO audit,
  structured data, JavaScript reliability (after research). Full update
  signing needs a key only the owner holds: ask him.
- Branch per version, PR, CI green, merge, tag `v<VERSION>` (VERSION in
  `server.py`).
- 1.1.2 plan written (2026-09-28): `docs/PLAN-1.1.2.md`, based on
  `docs/research/crawler-research.md` (trafilatura main text, site-wide
  boilerplate removal, URL normalisation, canonical following, exact and
  near-duplicate marking, trap limits, hard page cap, Retry-After and
  Crawl-delay, plus the safety fixes and a smoke crawl of the built exe in
  the release workflow). Next: supervisor review, then build, then tag v1.1.2.
- 1.2.0 (the Slush redesign with orbs) shipped first, merged as 9cb4739. The
  fixes planned as 1.1.2 ship as 1.2.1 from branch `fix/1.1.2-crawler-and-safety`
  (name kept), PR #1, with main merged in; `CHANGELOG.md` lists them. Built in
  the plan's order, steps 1-13 with the supervisor's changes; step 14 = VERSION
  1.2.1, docs, a books.toscrape.com sanity crawl, the real 1.2.0 -> 1.2.1
  update test on Windows. Merge and tag are left to the owner/supervisor.
- 1.2.2 (branch `fix/1.2.2-js-routes`, PR #3; plan and root-cause evidence in
  `docs/PLAN-1.2.2.md`): textifydigitals.com's nginx answers every path with 200
  and the same pre-rendered home page; the React app draws the real page in the
  browser. Render JavaScript now waits for networkidle (max 10 s). Before the
  first page the spider downloads a made-up address directly (no row, no cap,
  no links); when the plain start page is byte-identical and both are 200, it
  notes `same_page_for_every_address` and switches to rendering (falls back
  and says so when Chromium is missing). Sitemap pages wait for that decision.
  The check and the decision are written to `summary.json` at once (Stop kills
  the crawl), so a resume keeps them. Rows carry requested/final URL, redirect
  chain, response bytes and sha256, rendered, and `suspicious: SAME_RESPONSE`;
  `canonical_to_home` is noted when most pages name / as canonical. Owner
  additions: a per-user Inno Setup installer (`installer/WebsiteCrawler.iss`,
  `WebsiteCrawler-Setup.exe`, second release asset; the zip the updater uses is
  unchanged), smoke-tested on every PR (silent install, start, uninstall).
  Live check (cap 8, no --render-js): switched by itself, 8 different pages.
  Merge and tag are left to the owner.
