import csv
import io
import json
import os
import shutil
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from server import app, JOBS_DIR

client = TestClient(app)

# Local Mock Server for Testing Crawls
class MockHTMLHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            content = """<!DOCTYPE html>
<html>
<head><title>Test Home Page</title><meta name="description" content="Welcome to test site"></head>
<body>
  <h1>Main Heading</h1>
  <h2>Sub Heading</h2>
  <p>This is a test page with clean text for crawling tests.</p>
  <a href="/about.html">About Page</a>
  <a href="/missing.html">Broken Page</a>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        elif self.path == "/about.html":
            content = """<!DOCTYPE html>
<html>
<head><title>About Us Page</title></head>
<body>
  <h1>About Our Company</h1>
  <p>Detailed information about our company and services.</p>
  <a href="/">Home</a>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        elif self.path == "/dynamic.html":
            content = """<!DOCTYPE html>
<html>
<head><title>Dynamic SPA Page</title></head>
<body>
  <h1>Client Rendered Site</h1>
  <div id="target">Static Unrendered Placeholder</div>
  <script>
    document.getElementById('target').innerText = 'DYNAMIC_JS_LOADED_SUCCESS';
  </script>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        elif self.path == "/sitemap.xml":
            content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>http://127.0.0.1:9999/</loc></url>
  <url><loc>http://127.0.0.1:9999/about.html</loc></url>
</urlset>"""
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def log_message(self, format, *args):
        pass  # Suppress HTTP server output in test logs


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 9999), MockHTMLHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:9999"
    server.shutdown()


def test_invalid_job_requests():
    # Test missing job
    res = client.get("/api/jobs/non_existent_job_12345")
    assert res.status_code == 404

    # Test invalid start request parameters
    res = client.post("/api/jobs/start", json={"url": "https://example.com", "max_pages": -5})
    assert res.status_code == 422


def test_full_crawl_lifecycle_and_exports(mock_server):
    seed_url = f"{mock_server}/"
    job_name = "e2e_mock_test_job"

    # Start Crawl
    start_payload = {
        "url": seed_url,
        "job_name": job_name,
        "preset": "quick",
        "max_pages": 10,
        "max_depth": 2,
        "minutes": 1.0,
        "delay": 0.1,
        "concurrency": 1,
        "use_sitemap": True,
    }

    start_res = client.post("/api/jobs/start", json=start_payload)
    assert start_res.status_code == 200
    data = start_res.json()
    assert data["status"] == "success"
    job_id = data["job_id"]
    assert job_id == job_name

    # Poll status until finished or max 60 seconds (Scrapy start-up alone is slow on WSL /mnt/c)
    status = "running"
    for _ in range(120):
        time.sleep(0.5)
        detail_res = client.get(f"/api/jobs/{job_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        status = detail_data["status"]
        if status in ["completed", "stopped", "failed"]:
            break

    assert status == "completed"
    assert detail_data["pages_saved"] >= 2

    # Verify Results API & Pagination
    results_res = client.get(f"/api/jobs/{job_id}/results?page=1&limit=10")
    assert results_res.status_code == 200
    rdata = results_res.json()
    assert rdata["total"] >= 2
    assert len(rdata["items"]) >= 2

    # Verify error pages are saved and the status filter finds them
    notfound = client.get(f"/api/jobs/{job_id}/results?status_code=404").json()
    assert [item["url"] for item in notfound["items"]] == [f"{mock_server}/missing.html"]

    # Verify Search Filtering
    search_res = client.get(f"/api/jobs/{job_id}/results?search=About")
    assert search_res.status_code == 200
    sdata = search_res.json()
    assert sdata["total"] >= 1
    assert any("About" in item.get("title", "") or "about" in item.get("url", "") for item in sdata["items"])

    # Verify CSV Export
    csv_res = client.get(f"/api/jobs/{job_id}/export?format=csv")
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    csv_text = csv_res.text
    assert "url,status,title" in csv_text
    assert "Test Home Page" in csv_text or "About Us Page" in csv_text

    # Verify JSON Export
    json_res = client.get(f"/api/jobs/{job_id}/export?format=json")
    assert json_res.status_code == 200
    assert json_res.headers["content-type"].startswith("application/json")
    json_items = json_res.json()
    assert isinstance(json_items, list)
    assert len(json_items) >= 2


def test_stop_job(mock_server):
    seed_url = f"{mock_server}/"
    job_name = "e2e_stop_test_job"

    start_payload = {
        "url": seed_url,
        "job_name": job_name,
        "max_pages": 100,
        "max_depth": 5,
        "minutes": 10.0,
        "delay": 2.0,
    }

    start_res = client.post("/api/jobs/start", json=start_payload)
    assert start_res.status_code == 200

    # Trigger stop immediately
    stop_res = client.post(f"/api/jobs/{job_name}/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "success"

    # Verify status reflects stopped
    detail_res = client.get(f"/api/jobs/{job_name}")
    assert detail_res.json()["status"] in ["stopped", "completed"]


def test_js_rendering_crawl(mock_server):
    seed_url = f"{mock_server}/dynamic.html"
    job_name = f"e2e_js_rendered_job_{int(time.time())}"

    start_payload = {
        "url": seed_url,
        "job_name": job_name,
        "preset": "quick",
        "max_pages": 5,
        "max_depth": 1,
        "minutes": 1.0,
        "delay": 0.1,
        "concurrency": 1,
        "use_sitemap": False,
        "render_js": True,
    }

    start_res = client.post("/api/jobs/start", json=start_payload)
    assert start_res.status_code == 200
    job_id = start_res.json()["job_id"]

    # Poll status until finished or max 60 seconds
    status = "running"
    for _ in range(120):
        time.sleep(0.5)
        detail_res = client.get(f"/api/jobs/{job_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        status = detail_data["status"]
        if status in ["completed", "stopped", "failed"]:
            break

    assert status == "completed"
    assert detail_data["render_js"] is True
    assert detail_data["pages_saved"] >= 1

    # Verify that the extracted text contains the JS-injected string
    results_res = client.get(f"/api/jobs/{job_id}/results?limit=5")
    assert results_res.status_code == 200
    items = results_res.json()["items"]
    assert len(items) >= 1
    dynamic_page = next((item for item in items if "dynamic.html" in item["url"]), None)
    assert dynamic_page is not None
    assert "DYNAMIC_JS_LOADED_SUCCESS" in dynamic_page["text"]


def test_unreachable_site_is_failed_not_completed():
    job_name = f"e2e_unreachable_{int(time.time())}"
    res = client.post("/api/jobs/start", json={"url": "http://127.0.0.1:1/", "job_name": job_name, "delay": 0.1, "use_sitemap": False})
    assert res.status_code == 200
    for _ in range(120):
        time.sleep(0.5)
        status = client.get(f"/api/jobs/{job_name}").json()["status"]
        if status != "running":
            break
    assert status == "failed"
