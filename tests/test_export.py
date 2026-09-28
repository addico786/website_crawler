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
