"""Shared helpers for crawl tests: serve a site on 127.0.0.1 and run crawl.py against it."""
import json
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SITE = Path(__file__).resolve().parent / "fixtures" / "site"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def serve(handler):
    """Start `handler` on a free 127.0.0.1 port; returns the running server."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def fixture_site():
    server = serve(partial(QuietHandler, directory=str(FIXTURE_SITE)))
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture
def crawl(tmp_path):
    """crawl(seed, *crawl_py_args) runs one crawl to the end and returns its rows."""
    def run(seed, *args, job=None):
        job = Path(job or tmp_path / "job")
        job.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(ROOT / "crawl.py"), seed, "--job", str(job), "--delay", "0", "--minutes", "2", *args]
        with open(job / "job.log", "a", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=240, check=True)
        results = job / "results.jsonl"
        if not results.exists():
            return []
        return [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line.strip()]
    return run
