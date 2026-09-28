# 🕷️ Polite Website Crawler & Visual Dashboard

A powerful, polite, and user-friendly web crawler and data extractor featuring a **modern visual dashboard** designed for non-technical users, powered by Scrapy and FastAPI.

## Install on Windows

**Download [`WebsiteCrawler-Setup.exe`](https://github.com/addico786/website_crawler/releases/latest) and double-click it.**

If Windows shows "Windows protected your PC", click More info → Run anyway (the app is not code-signed yet).

Already installed? Use Check for Updates in the app.

---

## What is new in 1.2.1

- **Less redundant data**: the main text of each page comes from trafilatura, so listing pages keep all their items; text repeated across most pages (banners, side blocks) is found once per job and left out of the dashboard and exports; URL variants and `rel=canonical` twins are fetched once; exact and near-duplicate pages are marked; endless calendars and loops are skipped; a page cap of 30 saves exactly 30 pages.
- **A result line** at the end of every crawl: pages, duplicates, near duplicates, boilerplate blocks and trap URLs skipped (also in `summary.json`).
- **Safer**: the dashboard refuses other sites' requests, updates are installed only when their sha256 matches the digest GitHub publishes, and CSV exports cannot run spreadsheet formulas.

Full list: [CHANGELOG.md](CHANGELOG.md).

---

## 🌟 Key Features

- **🎨 Non-Technical Visual Dashboard**: No command line required! Start crawls, monitor progress, and view extracted data directly in your browser.
- **🌐 Optional JavaScript Rendering (Playwright)**: Renders client-side dynamic JavaScript (React, Vue, Angular, Next.js single-page applications) using headless Chromium. Keep standard HTTP crawling for blazing fast static site scans or toggle JS rendering with 1 click.
- **⚡ 1-Click Crawl Presets**:
  - **Quick Crawl**: Fast 100-page scan (5 min limit) for rapid testing.
  - **Deep Crawl**: Comprehensive 1,000-page crawl (60 min limit) for thorough site mapping.
  - **Custom Crawl**: Fully customizable limits for pages, link depth, request delay, and sitemap parsing.
- **📊 Interactive Data Explorer**:
  - Search page titles, URLs, headings, and extracted text.
  - Filter by HTTP status code (200 OK, 404, 500).
  - Inspect page details (meta descriptions, H1/H2 headings, canonical URLs, and cleaned text).
- **📥 1-Click Exports**: Download page results in **CSV** or **JSON** format with a single click. The CSV marks duplicates (`duplicate_of`, `near_duplicate_of`) and says where the text came from (`text_source`).
- **📡 Real-Time Console Stream**: Live streaming log viewer directly in the browser via Server-Sent Events (SSE).
- **🛡️ Polite & Safe**: Automatically obeys `robots.txt`, auto-throttles requests, handles rate limits, and caps page limits to protect target servers.
- **🔗 Smart Link Handling**: Stays on the site's own host (plus `www.`), follows the start URL if it redirects to another domain, reads sitemaps listed in `robots.txt` (including sitemap indexes and `.xml.gz`), respects `rel="nofollow"` and `<meta name="robots" content="nofollow">`, strips click-tracking tags (`utm_*`, `gclid`, `fbclid`…) so the same page isn't saved twice, skips files (PDF, images, video, installers, office docs), and never follows links out of error pages. Broken pages are saved with their status code and the page that links to them (**Found On**).

---

## 🚀 Quick Start (For Non-Technical Users)

### Option A: Windows App (no Python needed)
1. Download `WebsiteCrawler-Setup.exe` from the latest [GitHub Release](https://github.com/addico786/website_crawler/releases/latest) and double-click it. It installs for your Windows user only (no admin prompt) into `%LOCALAPPDATA%\Programs\WebsiteCrawler`, with a Start-menu shortcut and, if you keep it ticked, a desktop shortcut. If SmartScreen says "Windows protected your PC", click More info → Run anyway (the app is not code-signed yet).
2. Open **Website Crawler**. The dashboard opens in its own window (Edge WebView2, built into Windows 10/11). Closing the window quits the app and stops any running crawls.

Your crawl data is stored in the `jobs` folder inside the install folder, next to `WebsiteCrawler.exe`. The first launch downloads Chromium (about 150-300 MB) in the background for "Render JavaScript" crawls, into `%LOCALAPPDATA%\ms-playwright`. To uninstall, use Apps & features (Settings → Apps); it asks before deleting your crawl results. The release also carries `WebsiteCrawler-windows.zip`, the same app without an installer: that is what **Check for Updates** downloads.

**Updates:** click **Check for Updates** at the bottom of the dashboard. If a newer version exists, the app downloads it, checks its sha256 against the digest GitHub publishes for the release, restarts itself, and the page reloads. Without a matching digest it installs nothing and offers the release page instead. Your `jobs` folder is kept. Stop any running crawls first.

### Option B: Windows from source (1-Click)
Double-click **`start_dashboard.bat`** in the project folder. It will set up the environment automatically and open the dashboard in your default browser at:
👉 **[http://localhost:8000](http://localhost:8000)**

### Option C: Linux / macOS / WSL
Open a terminal in the project folder and run:
```bash
chmod +x start_dashboard.sh
./start_dashboard.sh
```
Then open **[http://localhost:8000](http://localhost:8000)** in your web browser.

---

## 🖥️ How to Use the Dashboard

1. Click **"+ New Crawl"** in the top right.
2. Enter the website target URL (e.g. `https://example.com`).
3. Select a preset (**Quick Crawl** or **Deep Crawl**) or choose **Custom** to set specific page/depth limits.
4. Click **"Start Crawl Now"**.
5. Watch live progress on the dashboard. Click **"Live Console"** anytime to view the live crawler logs.
6. Explore extracted web pages in the interactive data table or click **"Export Data"** to download as CSV or JSON!

---

## 🛠️ Developer & CLI Usage

If you prefer using the command line or integrating into existing workflows:

### 1. Manual Server Launch
```bash
# Activate environment
. env/bin/activate  # On Linux/WSL
# or env\Scripts\activate on Windows

# Install requirements
pip install -r requirements.txt

# (Optional) Install Playwright browser for JavaScript rendering
playwright install chromium

# Run dashboard API server
python server.py
```

### 2. Command Line Crawler (CLI)
You can run crawls directly via the terminal with standard HTTP or JavaScript rendering:
```bash
# Standard fast crawl
python crawl.py https://example.com --minutes 60 --job jobs/my_job_name --delay 1.0 --max-pages 500

# JavaScript-rendered crawl (Playwright Chromium)
python crawl.py https://example.com --render-js --minutes 10 --job jobs/spa_job_name --delay 1.0
```

### 3. Run Automated Tests
```bash
python -m playwright install chromium   # once, for the JavaScript rendering test
python -m pytest
```
The tests crawl local fixture sites on 127.0.0.1 only. GitHub Actions runs them on every pull request, and builds and smoke-tests the Windows app (`tests/smoke_frozen.py`).

### 4. Building & Releasing the Windows App
The app is packaged with [PyInstaller](https://pyinstaller.org/) (`--onedir`). PyInstaller cannot cross-compile, so build on Windows:
```bat
build_exe.bat
```
This creates `dist\WebsiteCrawler\WebsiteCrawler.exe`, `dist\WebsiteCrawler-windows.zip` and, when [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed, the installer `dist\WebsiteCrawler-Setup.exe` (`installer\WebsiteCrawler.iss`, given `VERSION` from `server.py`). The build is defined in `WebsiteCrawler.spec`: the window app plus `WebsiteCrawlerWorker.exe`, a console twin that runs crawls hidden so no console windows pop up.

To publish an update that users receive through **Check for Updates**:
1. Bump `VERSION` in `server.py` (e.g. `1.2.1`), add it to `CHANGELOG.md`, and commit.
2. Tag and push: `git tag v1.2.1 && git push origin v1.2.1`.
3. The GitHub Actions workflow (`.github/workflows/release.yml`) builds on Windows, smoke-tests the built app and the installer (silent install, start, uninstall), and only then publishes `WebsiteCrawler-Setup.exe` and `WebsiteCrawler-windows.zip` as a Release. The updater installs only the zip, by that exact name, with a sha256 digest (GitHub adds it to release assets).

The updater reads `https://api.github.com/repos/<UPDATE_REPO>/releases/latest` (`UPDATE_REPO` in `server.py`), so the repository must be **public**. Drafts and pre-releases are ignored. If the source repo is private, publish the release zips to a separate public repo and point `UPDATE_REPO` at it.

---

## 📁 Project Architecture & Structure

```text
website_crawler/
├── server.py             # FastAPI backend (REST API, process runner, SSE log stream, updates)
├── app.py                # Entry point of the Windows app (own window via pywebview)
├── crawl.py              # CLI launcher for Scrapy crawler
├── crawler.sh            # Interactive CLI launcher
├── polite_crawler/       # Scrapy spider, settings, and JSONL export pipelines
│   ├── spiders/site.py   # Main SiteSpider logic (link extraction, page keys, page cap)
│   ├── maintext.py       # Main text with trafilatura, with a fallback
│   ├── textblocks.py     # Site-wide boilerplate (boilerplate.json), shared with server.py
│   ├── fingerprints.py   # content_hash and SimHash near-duplicates
│   ├── traps.py          # Crawler trap rules and the suspected-trap report
│   ├── pipelines.py      # Writes results.jsonl, boilerplate.json and summary.json
│   └── settings.py       # Auto-throttling & politeness defaults
├── static/               # Visual Web Dashboard UI
│   ├── index.html        # Single Page Dashboard Interface
│   ├── app.css           # Slush design styling & layout
│   ├── app.js            # Client-side SPA logic & real-time updates
│   └── orbs.js           # Thinking-orbs loaders (vendored engine in vendor/)
├── start_dashboard.bat   # 1-Click Windows launcher script
├── start_dashboard.sh    # 1-Click Linux/WSL launcher script
├── build_exe.bat         # Builds the Windows app with PyInstaller
├── WebsiteCrawler.spec   # PyInstaller build: window app + hidden crawl worker
├── installer/            # Inno Setup script for WebsiteCrawler-Setup.exe
├── .github/workflows/    # Tests on Linux; Windows build + smoke on PRs; tag v* -> GitHub Release
├── tests/                # Crawler, dashboard guard, export and updater tests; fixture site
├── test_smoke.py         # Automated smoke & API unit tests
├── test_e2e.py           # End-to-end crawl tests against a local mock site
├── CHANGELOG.md          # What changed in each version
├── .gitignore            # Git exclusion settings
├── .env.example          # Environment configuration template
└── requirements.txt      # Python dependencies
```

---

## ⚖️ Responsible & Polite Crawling

Always make sure you have permission to crawl a target website. This crawler automatically respects `robots.txt` rules and includes built-in request delay throttling. Do not use this tool on sites that prohibit automated crawling in their Terms of Service.
