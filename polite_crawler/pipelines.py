"""Write results and a human-readable summary beside each persistent job."""
import json
from datetime import datetime, timezone
from pathlib import Path

from scrapy import signals


class JobOutputPipeline:
    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls(crawler)
        crawler.signals.connect(pipeline.spider_closed, signal=signals.spider_closed)
        return pipeline

    def __init__(self, crawler):
        self.crawler = crawler
        self.saved = 0

    def open_spider(self, spider):
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.job_dir = Path(spider.job_dir)
        self.file = (self.job_dir / "results.jsonl").open("a", encoding="utf-8")

    def process_item(self, item, spider):
        self.file.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
        self.file.flush()
        self.saved += 1
        return item

    def spider_closed(self, spider, reason):
        if hasattr(self, "file"):
            self.file.close()
        stats = self.crawler.stats.get_stats()
        status_counts = {
            key.rsplit("/", 1)[-1]: value
            for key, value in stats.items()
            if key.startswith("downloader/response_status_count/")
        }
        summary = {
            "seed_url": spider.start_urls[0],
            "allowed_hosts": spider.allowed_domains,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "finish_reason": reason,
            "pages_saved_this_run": self.saved,
            "requests_sent": stats.get("downloader/request_count", 0),
            "responses_by_status": status_counts,
            "request_errors": stats.get("downloader/exception_count", 0),
            "results_file": "results.jsonl",
        }
        (self.job_dir / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
