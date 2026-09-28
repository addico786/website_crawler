# 1.2.0: to do before release (from the screenshot check, 2026-09-28)

1. Rebase on main after 1.1.2 merges. index.html keeps this branch's markup and takes
   1.1.2's `?v=<VERSION>` on app.js and app.css; add the same to orbs.js (and its
   vendor import if cached). Keep 1.1.2's JSON bodies on writes and the release-page
   fallback when download_url is null. Re-check the server.py MIME lines next to the
   new Host/Origin middleware.
2. The running orb is too faint: pale grey dots at 20 px on the card and 64 px in the
   detail panel. Use black ink (the Slush text colour) and make the detail orb larger
   (about 96 px), so it reads as alive at a glance.
3. While a crawl runs, the results table says "No pages found for this job" although
   pages are saved (the table does not refresh during a crawl). Refresh it on the
   existing 4-second poll while the job is running, keeping the page, filter and
   search.
4. Modals: close on Escape, trap focus, and return focus to the opener.
5. Build the Windows exe (the PR smoke from 1.1.2 covers this) and look at the real
   window once, then bump VERSION to 1.2.0.
