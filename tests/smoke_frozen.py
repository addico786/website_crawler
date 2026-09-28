"""Smoke test of the built Windows app, run by release.yml before anything is published.

1. WebsiteCrawlerWorker.exe --crawl crawls tests/fixtures/site/ (served on 127.0.0.1);
   fails unless enough pages are saved.
2. WebsiteCrawler.exe --server-only must answer / and /api/version with this VERSION.
3. The release zip beside it must hold WebsiteCrawler/WebsiteCrawler.exe (the updater's layout).
4. WebsiteCrawler-Setup.exe must install silently into a temporary folder, the installed app must
   answer /api/version, and the uninstaller must remove the program files again.

Usage: python tests/smoke_frozen.py [dist/WebsiteCrawler]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SITE = ROOT / "tests" / "fixtures" / "site"
DIST = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "WebsiteCrawler").resolve()
VERSION = re.search(r'^VERSION = "(.*)"', (ROOT / "server.py").read_text(encoding="utf-8"), re.M).group(1)
PORT = 8765


def fail(message, log=None):
    if log and Path(log).exists():
        print(Path(log).read_text(encoding="utf-8", errors="replace")[-8000:])
    print(f"SMOKE FAILED: {message}")
    sys.exit(1)


def smoke_crawl(job):
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURE_SITE))
    site = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    seed = f"http://127.0.0.1:{site.server_port}/"
    log = job / "job.log"
    command = [str(DIST / "WebsiteCrawlerWorker.exe"), "--crawl", seed, "--job", str(job),
               "--delay", "0", "--minutes", "3", "--max-pages", "50"]
    with open(log, "w", encoding="utf-8") as out:
        code = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT, timeout=600).returncode
    site.shutdown()
    if code:
        fail(f"worker exited with {code}", log)
    results = job / "results.jsonl"
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line.strip()] if results.exists() else []
    for row in rows:
        print(f"  {row['status']} {row['url']} words={row.get('word_count')} text_source={row.get('text_source')}")
    if len(rows) < 4:
        fail(f"only {len(rows)} pages saved", log)
    if not any(row.get("text_source") == "trafilatura" for row in rows):
        fail("no page's main text came from trafilatura (its data files may be missing from the build)", log)
    if not (job / "boilerplate.json").exists():
        fail("no boilerplate.json written at the end of the crawl", log)
    print(f"Crawl OK: {len(rows)} pages, boilerplate: {(job / 'boilerplate.json').read_text(encoding='utf-8')}")


def smoke_zip():
    # The updater unpacks this zip and looks for WebsiteCrawler.exe in its WebsiteCrawler folder.
    zip_path = DIST.parent / "WebsiteCrawler-windows.zip"
    if not zip_path.exists():
        fail(f"{zip_path} was not built")
    names = set(zipfile.ZipFile(zip_path).namelist())
    for needed in ("WebsiteCrawler/WebsiteCrawler.exe", "WebsiteCrawler/WebsiteCrawlerWorker.exe"):
        if needed not in names:
            fail(f"{needed} is missing from {zip_path.name}")
    print(f"Zip OK: {len(names)} files")


def smoke_installer():
    setup = DIST.parent / "WebsiteCrawler-Setup.exe"
    if not setup.exists():
        fail(f"{setup} was not built")
    shortcut = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Website Crawler.lnk"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        target = Path(directory) / "WebsiteCrawler"
        command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CURRENTUSER", "/NORESTART", f"/DIR={target}"]
        code = subprocess.run(command, timeout=600).returncode
        if code:
            fail(f"the installer exited with {code}")
        if not (target / "WebsiteCrawler.exe").exists() or not shortcut.exists():
            fail(f"the installer did not install WebsiteCrawler.exe and its Start menu shortcut into {target}")
        smoke_server(target)
        # The uninstaller runs from a copy in %TEMP% and returns at once: wait for it to finish.
        subprocess.run([str(target / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=300)
        program = ["WebsiteCrawler.exe", "WebsiteCrawlerWorker.exe", "_internal", "unins000.exe"]
        for _ in range(120):
            left = [name for name in program if (target / name).exists()]
            if not left and not shortcut.exists():
                break
            time.sleep(1)
        else:
            fail(f"the uninstaller left {left or 'the Start menu shortcut'} behind")
        print(f"Installer OK: {setup.stat().st_size / 1e6:.1f} MB; installed, ran and uninstalled"
              f"{'' if target.exists() else ' (folder removed)'}")


def smoke_server(folder=DIST):
    env = {**os.environ, "PORT": str(PORT)}
    proc = subprocess.Popen([str(folder / "WebsiteCrawler.exe"), "--server-only"], env=env)
    try:
        base = f"http://127.0.0.1:{PORT}"
        for _ in range(120):
            try:
                version = json.load(urllib.request.urlopen(base + "/api/version", timeout=2))["version"]
                break
            except OSError:
                time.sleep(1)
        else:
            fail("the dashboard did not answer /api/version", folder / "app.log")
        if version != VERSION:
            fail(f"/api/version says {version}, server.py says {VERSION}")
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        if "<html" not in page.lower():
            fail("/ did not return the dashboard page")
        print(f"Server OK: version {version} from {folder}")
    finally:
        # /T also stops the Chromium installer the app starts in the background.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        for _ in range(20):  # the next check starts another app on this port
            try:
                urllib.request.urlopen(base + "/api/version", timeout=1)
                time.sleep(0.5)
            except OSError:
                break


if __name__ == "__main__":
    smoke_zip()
    with tempfile.TemporaryDirectory() as directory:
        smoke_crawl(Path(directory))
    smoke_server()
    smoke_installer()
    print("Smoke test passed.")
