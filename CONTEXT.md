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
- Plan: 1.1.2 = fixes (page cap, full text of listing pages, dashboard
  protection, CSV safety, update checksum from GitHub's asset digest,
  real contact address, CI on push and pull requests); 1.2.0 = SEO audit,
  structured data, JavaScript reliability (after research). Full update
  signing needs a key only the owner holds: ask him.
- Branch per version, PR, CI green, merge, tag `v<VERSION>` (VERSION in
  `server.py`).
