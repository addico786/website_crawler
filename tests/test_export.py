import csv
import io
import json
import shutil

from fastapi.testclient import TestClient

from server import JOBS_DIR, app

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_csv_export_escapes_formulas():
    job = JOBS_DIR / "test_csv_formulas"
    job.mkdir(parents=True, exist_ok=True)
    try:
        row = {
            "url": "https://example.com/a", "status": 200, "title": '=HYPERLINK("http://evil.test","x")',
            "description": "+1 555", "headings": ["-2+3", "@SUM(A1)"], "text": "\tcmd", "found_on": "\rx",
            "word_count": 2, "links_found": 0, "canonical_url": "https://example.com/a", "crawled_at": "2026-09-28",
        }
        (job / "results.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        response = client.get("/api/jobs/test_csv_formulas/export?format=csv")
        assert response.status_code == 200
        exported = next(csv.DictReader(io.StringIO(response.text)))
        assert exported["title"] == "'" + row["title"]
        assert exported["description"] == "'+1 555"
        assert exported["headings"] == "'-2+3 | @SUM(A1)"
        assert exported["text"] == "'\tcmd"
        assert exported["found_on"] == "'\rx"
        assert exported["url"] == "https://example.com/a" and exported["status"] == "200"
        # JSON is data, not a spreadsheet: left as it is.
        assert client.get("/api/jobs/test_csv_formulas/export?format=json").json()[0]["title"] == row["title"]
    finally:
        shutil.rmtree(job, ignore_errors=True)


def test_csv_export_has_the_duplicate_and_text_source_columns():
    job = JOBS_DIR / "test_csv_columns"
    job.mkdir(parents=True, exist_ok=True)
    try:
        new = {"url": "https://example.com/b", "status": 200, "text": "Body", "text_source": "trafilatura",
               "content_hash": "ab" * 32, "duplicate_of": "https://example.com/a", "near_duplicate_of": None}
        old = {"url": "https://example.com/old", "status": 200, "text": "Saved by 1.1.1"}  # no such fields
        (job / "results.jsonl").write_text(json.dumps(new) + "\n" + json.dumps(old) + "\n", encoding="utf-8")
        response = client.get("/api/jobs/test_csv_columns/export?format=csv")
        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows[0]["text_source"] == "trafilatura" and rows[0]["content_hash"] == "ab" * 32
        assert rows[0]["duplicate_of"] == "https://example.com/a" and rows[0]["near_duplicate_of"] == ""
        assert rows[1]["url"] == "https://example.com/old" and rows[1]["duplicate_of"] == "" and rows[1]["text_source"] == ""
        assert list(rows[0])[-1] == "text"  # the long column stays last
    finally:
        shutil.rmtree(job, ignore_errors=True)


def test_csv_export_has_the_response_columns():
    job = JOBS_DIR / "test_csv_response_columns"
    job.mkdir(parents=True, exist_ok=True)
    try:
        new = {"url": "https://example.com/new", "status": 200, "text": "Body", "requested_url": "https://example.com/old",
               "final_url": "https://example.com/new", "redirect_chain": ["https://example.com/old", "https://example.com/older"],
               "response_bytes": 1234, "response_sha256": "cd" * 32, "rendered": False}
        old = {"url": "https://example.com/a", "status": 200, "text": "Saved by 1.2.1"}  # no such fields
        (job / "results.jsonl").write_text(json.dumps(new) + "\n" + json.dumps(old) + "\n", encoding="utf-8")
        rows = list(csv.DictReader(io.StringIO(client.get("/api/jobs/test_csv_response_columns/export?format=csv").text)))
        assert rows[0]["requested_url"] == "https://example.com/old" and rows[0]["final_url"] == "https://example.com/new"
        assert rows[0]["redirect_chain"] == "https://example.com/old -> https://example.com/older"
        assert rows[0]["response_bytes"] == "1234" and rows[0]["response_sha256"] == "cd" * 32 and rows[0]["rendered"] == "False"
        assert rows[1]["requested_url"] == rows[1]["redirect_chain"] == rows[1]["response_sha256"] == ""
        assert list(rows[0])[-1] == "text"
    finally:
        shutil.rmtree(job, ignore_errors=True)
