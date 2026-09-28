"""Smoke test of the built Windows app, run by release.yml before anything is published.

1. WebsiteCrawlerWorker.exe --crawl crawls tests/fixtures/site/ (served on 127.0.0.1);
   fails unless enough pages are saved.
2. WebsiteCrawler.exe --server-only must answer / and /api/version with this VERSION.

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
        print(f"  {row['status']} {row['url']} words={row.get('word_count')}")
    if len(rows) < 4:
        fail(f"only {len(rows)} pages saved", log)
    print(f"Crawl OK: {len(rows)} pages")


def smoke_server():
    env = {**os.environ, "PORT": str(PORT)}
    proc = subprocess.Popen([str(DIST / "WebsiteCrawler.exe"), "--server-only"], env=env)
    try:
        base = f"http://127.0.0.1:{PORT}"
        for _ in range(120):
            try:
                version = json.load(urllib.request.urlopen(base + "/api/version", timeout=2))["version"]
                break
            except OSError:
                time.sleep(1)
        else:
            fail("the dashboard did not answer /api/version", DIST / "app.log")
        if version != VERSION:
            fail(f"/api/version says {version}, server.py says {VERSION}")
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        if "<html" not in page.lower():
            fail("/ did not return the dashboard page")
        print(f"Server OK: version {version}")
    finally:
        # /T also stops the Chromium installer the app starts in the background.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        smoke_crawl(Path(directory))
    smoke_server()
    print("Smoke test passed.")
