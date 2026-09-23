# 🕷️ Polite Website Crawler & Visual Dashboard

A powerful, polite, and user-friendly web crawler and data extractor featuring a **modern visual dashboard** designed for non-technical users, powered by Scrapy and FastAPI.

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
- **📥 1-Click Exports**: Download page results in **CSV** or **JSON** format with a single click.
- **📡 Real-Time Console Stream**: Live streaming log viewer directly in the browser via Server-Sent Events (SSE).
- **🛡️ Polite & Safe**: Automatically obeys `robots.txt`, auto-throttles requests, handles rate limits, and caps page limits to protect target servers.
- **🔗 Smart Link Handling**: Stays on the site's own host (plus `www.`), follows the start URL if it redirects to another domain, reads sitemaps listed in `robots.txt` (including sitemap indexes and `.xml.gz`), respects `rel="nofollow"` and `<meta name="robots" content="nofollow">`, strips click-tracking tags (`utm_*`, `gclid`, `fbclid`…) so the same page isn't saved twice, skips files (PDF, images, video, installers, office docs), and never follows links out of error pages. Broken pages are saved with their status code and the page that links to them (**Found On**).

---

## 🚀 Quick Start (For Non-Technical Users)

### Option A: Windows App (no Python needed)
1. Download `WebsiteCrawler-windows.zip` from the latest [GitHub Release](https://github.com/addico786/website_crawler/releases/latest).
2. Unzip it anywhere you can write to (e.g. Desktop or Documents — not `Program Files`).
3. Double-click **`WebsiteCrawler.exe`**. The dashboard opens in its own window (Edge WebView2, built into Windows 10/11). Closing the window quits the app and stops any running crawls.

Your crawl data is stored in the `jobs` folder next to the `.exe`. The first launch downloads Chromium (~150 MB) in the background for "Render JavaScript" crawls.

**Updates:** click **Check for Updates** at the bottom of the dashboard. If a newer version exists, the app downloads it, restarts itself, and the page reloads. Your `jobs` folder is kept. Stop any running crawls first.

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
python -m pytest test_smoke.py test_e2e.py
```

### 4. Building & Releasing the Windows App
The app is packaged with [PyInstaller](https://pyinstaller.org/) (`--onedir`). PyInstaller cannot cross-compile, so build on Windows:
```bat
build_exe.bat
```
This creates `dist\WebsiteCrawler\WebsiteCrawler.exe` and `dist\WebsiteCrawler-windows.zip`. The build is defined in `WebsiteCrawler.spec`: the window app plus `WebsiteCrawlerWorker.exe`, a console twin that runs crawls hidden so no console windows pop up.

To publish an update that users receive through **Check for Updates**:
1. Bump `VERSION` in `server.py` (e.g. `1.1.0`) and commit.
2. Tag and push: `git tag v1.1.0 && git push origin v1.1.0`.
3. The GitHub Actions workflow (`.github/workflows/release.yml`) builds on Windows and publishes the zip as a Release.

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
│   ├── spiders/site.py   # Main SiteSpider logic (link extraction, text cleanup)
│   ├── pipelines.py      # Writes results.jsonl and summary.json
│   └── settings.py       # Auto-throttling & politeness defaults
├── static/               # Visual Web Dashboard UI
│   ├── index.html        # Single Page Dashboard Interface
│   ├── app.css           # Glassmorphism dark mode styling & layout
│   └── app.js            # Client-side SPA logic & real-time updates
├── start_dashboard.bat   # 1-Click Windows launcher script
├── start_dashboard.sh    # 1-Click Linux/WSL launcher script
├── build_exe.bat         # Builds the Windows app with PyInstaller
├── WebsiteCrawler.spec   # PyInstaller build: window app + hidden crawl worker
├── .github/workflows/    # Release workflow: tag v* -> Windows build -> GitHub Release
├── test_smoke.py         # Automated smoke & API unit tests
├── test_e2e.py           # End-to-end crawl tests against a local mock site
├── .gitignore            # Git exclusion settings
├── .env.example          # Environment configuration template
└── requirements.txt      # Python dependencies
```

---

## ⚖️ Responsible & Polite Crawling

Always make sure you have permission to crawl a target website. This crawler automatically respects `robots.txt` rules and includes built-in request delay throttling. Do not use this tool on sites that prohibit automated crawling in their Terms of Service.
