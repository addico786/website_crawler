import json
import shutil
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from polite_crawler.textblocks import find_boilerplate, load_boilerplate, strip_boilerplate, write_boilerplate
from server import JOBS_DIR, app

client = TestClient(app, base_url="http://127.0.0.1:8000")
BANNER = "Free delivery on every order over forty pounds."


def test_find_boilerplate_needs_half_the_pages_and_at_least_five():
    pages = [f"Page {n} heading\n{BANNER}\nBody of page {n}." for n in range(8)] + ["Only here.", ""]
    blocks, with_text = find_boilerplate(pages)
    assert blocks == [BANNER] and with_text == 9  # the empty text does not count
    # 4 pages: too few to tell a template from content.
    assert find_boilerplate(pages[:4]) == ([], 4)
    # On 5 of 12 pages: under half.
    assert find_boilerplate(pages[:5] + [f"Other {n}" for n in range(7)])[0] == []
    # Spacing does not make a block different; each page counts a block once.
    blocks, _ = find_boilerplate([f"  {BANNER}  \n{BANNER}\nx{n}" for n in range(5)])
    assert blocks == [BANNER]
    # Table rows are page data, even when every product shares them (books.toscrape.com).
    products = [f"Book {n}\n| UPC | {n:04x} |\n|---|---|\n| Tax | £0.00 |\n{BANNER}" for n in range(6)]
    assert find_boilerplate(products) == ([BANNER], 6)


def test_boilerplate_file_round_trip(tmp_path):
    assert load_boilerplate(tmp_path) == set()  # no file: raw text
    (tmp_path / "boilerplate.json").write_text("{not json", encoding="utf-8")
    assert load_boilerplate(tmp_path) == set()  # damaged file: raw text
    write_boilerplate(tmp_path, [BANNER], 8)
    assert load_boilerplate(tmp_path) == {BANNER}
    assert not (tmp_path / "boilerplate.json.tmp").exists()
    assert strip_boilerplate(f"Title\n  {BANNER}\nBody", {BANNER}) == "Title\nBody"


def test_dashboard_strips_boilerplate_when_reading():
    job = JOBS_DIR / "test_boilerplate_job"
    shutil.rmtree(job, ignore_errors=True)
    job.mkdir(parents=True)
    try:
        rows = [{"url": f"https://example.com/{n}", "status": 200, "text": f"Guide {n}\n{BANNER}\nfour words here {n}",
                 "word_count": 13, "links_found": 1} for n in range(3)]
        (job / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows) + '{"url": "cut sh', encoding="utf-8")
        # Without boilerplate.json the text is served as saved (and a half-written line is skipped).
        items = client.get("/api/jobs/test_boilerplate_job/results").json()["items"]
        assert len(items) == 3 and BANNER in items[0]["text"]

        write_boilerplate(job, [BANNER], 3)
        items = client.get("/api/jobs/test_boilerplate_job/results").json()["items"]
        assert items[0]["text"] == "Guide 0\nfour words here 0" and items[0]["word_count"] == 6
        assert client.get("/api/jobs/test_boilerplate_job/results?search=forty").json()["total"] == 0
        assert client.get("/api/jobs/test_boilerplate_job").json()["total_words"] == 18
        assert BANNER not in client.get("/api/jobs/test_boilerplate_job/export?format=csv").text
        assert BANNER not in client.get("/api/jobs/test_boilerplate_job/export?format=json").text
        # results.jsonl itself is never rewritten.
        assert (job / "results.jsonl").read_text(encoding="utf-8").count(BANNER) == 3
    finally:
        shutil.rmtree(job, ignore_errors=True)
