import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi.testclient import TestClient
from polite_crawler.pipelines import JobOutputPipeline
from polite_crawler.spiders.site import SiteSpider
from server import app, sanitize_job_name, JOBS_DIR

client = TestClient(app)


def test_spider_scope():
    spider = SiteSpider(start_url="https://www.example.com/docs", job_dir="jobs/example")
    assert spider.allowed_domains == ["example.com", "www.example.com"]
    assert spider.start_urls == ["https://www.example.com/docs"]


def test_job_output():
    with TemporaryDirectory() as directory:
        stats = SimpleNamespace(get_stats=lambda: {"downloader/request_count": 1})
        pipeline = JobOutputPipeline(SimpleNamespace(stats=stats))
        spider = SimpleNamespace(
            job_dir=directory,
            start_urls=["https://example.com"],
            allowed_domains=["example.com", "www.example.com"],
        )
        pipeline.open_spider(spider)
        pipeline.process_item({"url": "https://example.com", "text": "Hello"}, spider)
        pipeline.spider_closed(spider, "finished")
        assert '"url": "https://example.com"' in (Path(directory) / "results.jsonl").read_text()
        assert '"finish_reason": "finished"' in (Path(directory) / "summary.json").read_text()


def test_sanitize_job_name():
    name = sanitize_job_name("https://example.com/blog", "My Test Job!")
    assert name == "my_test_job_"

    auto_name = sanitize_job_name("https://sub.domain.org/path")
    assert "sub_domain_org_path" in auto_name


def test_api_overview_and_jobs_list():
    response = client.get("/api/stats/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "total_pages" in data

    response = client.get("/api/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data


def test_delete_job_endpoint():
    job_dir = JOBS_DIR / "temp_delete_smoke_job"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "results.jsonl").write_text('{"url": "https://example.com"}\n', encoding="utf-8")
    assert job_dir.exists()

    res = client.delete("/api/jobs/temp_delete_smoke_job")
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert not job_dir.exists()

    # Deleting non-existent job returns 404
    res_404 = client.delete("/api/jobs/temp_delete_smoke_job")
    assert res_404.status_code == 404


def test_job_id_cannot_escape_jobs_dir():
    assert client.get("/api/jobs/%2E%2E").status_code == 404
    assert client.delete("/api/jobs/%2E%2E").status_code == 404


def test_spider_stays_on_exact_host():
    spider = SiteSpider(start_url="https://example.com", job_dir="jobs/example")
    assert spider.in_scope("https://www.example.com/a")
    assert not spider.in_scope("https://signin.example.com/a")


def test_update_check(monkeypatch):
    import server

    assert server.parse_version("v1.10.0") > server.parse_version("1.9.3")
    release = {
        "tag_name": "v99.0.0",
        "html_url": "https://github.com/x/y/releases/tag/v99.0.0",
        "assets": [{"name": "WebsiteCrawler-windows.zip", "browser_download_url": "https://example.com/a.zip"}],
    }
    monkeypatch.setattr(server, "fetch_latest_release", lambda: release)
    data = client.get("/api/update/check").json()
    assert data["update_available"] and data["download_url"] == "https://example.com/a.zip"

    release["tag_name"] = f"v{server.VERSION}"
    assert client.get("/api/update/check").json()["update_available"] is False
    assert client.post("/api/update/install").status_code == 400  # not the packaged Windows app


def test_spider_link_rules():
    from scrapy.http import HtmlResponse, Request, TextResponse

    spider = SiteSpider(start_url="https://example.com", job_dir="jobs/does_not_exist")
    body = b"""<html><body>
      <a href="/a?utm_source=x&tag=1">tracked</a> <a href="/a?tag=1">same page</a>
      <a href="/setup.exe">binary</a> <a href="/p" rel="nofollow">nofollow</a>
      <a href="mailto:x@example.com">mail</a> <a href="https://sub.example.com/">subdomain</a>
      <a href="rel/child">relative</a></body></html>"""

    def crawl(url, status=200):
        request = Request(url, headers={"Referer": "https://example.com/"})
        return list(spider.parse(HtmlResponse(url, status=status, body=body, request=request)))

    out = crawl("https://example.com/page")
    followed = [r.url for r in out if isinstance(r, Request)]
    assert followed == ["https://example.com/a?tag=1", "https://example.com/rel/child"]
    assert out[0]["found_on"] == "https://example.com/"

    # Error pages are saved but their (relative) links are not followed: no /missing/rel/rel/... trap.
    out = crawl("https://example.com/missing/", status=404)
    assert [type(r) for r in out] == [dict] and out[0]["status"] == 404
    assert crawl("https://example.com/page#top") == []  # already saved

    robots = TextResponse("https://example.com/robots.txt", body=b"Sitemap: https://example.com/s.xml\n")
    assert [r.url for r in spider.parse_robots(robots)] == ["https://example.com/s.xml"]
    sitemap = TextResponse("https://example.com/s.xml", body=b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"><url><loc>https://example.com/b</loc>
      <image:image><image:loc>https://example.com/b.jpg</image:loc></image:image></url></urlset>""")
    assert [r.url for r in spider.parse_sitemap(sitemap)] == ["https://example.com/b"]
