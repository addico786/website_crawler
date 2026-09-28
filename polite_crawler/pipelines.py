"""Write results and a human-readable summary beside each persistent job."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from scrapy import signals
from scrapy.exceptions import DropItem

from polite_crawler.textblocks import find_boilerplate, write_boilerplate, write_json

logger = logging.getLogger(__name__)


def read_rows(path):
    """Every row of a results.jsonl, skipping a line cut short by a hard stop."""
    rows = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def read_summary(job_dir):
    """The job's summary.json (from an earlier run, or this one so far); {} when there is none."""
    try:
        summary = json.loads((Path(job_dir) / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return summary if isinstance(summary, dict) else {}


def update_summary(job_dir, fields):
    """Set some fields of summary.json now, keeping the rest."""
    write_json(Path(job_dir) / "summary.json", {**read_summary(job_dir), **fields})


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
        results = self.job_dir / "results.jsonl"
        # Backstop for the spider's page cap: never write more rows than the cap.
        self.max_pages = getattr(spider, "max_pages", 0)
        self.rows = sum(1 for line in results.open(encoding="utf-8") if line.strip()) if results.exists() else 0
        self.file = results.open("a", encoding="utf-8")

    def process_item(self, item, spider):
        if self.max_pages and self.rows >= self.max_pages:
            raise DropItem(f"page cap of {self.max_pages} reached")
        self.rows += 1
        self.file.write(json.dumps(dict(item), ensure_ascii=False) + "\n")
        self.file.flush()
        self.saved += 1
        return item

    def spider_closed(self, spider, reason):
        if hasattr(self, "file"):
            self.file.close()
        # Site-wide boilerplate, over every run of this job. Exact copies would count their blocks twice.
        rows = read_rows(self.job_dir / "results.jsonl")
        blocks, pages = find_boilerplate(row.get("text", "") for row in rows if not row.get("duplicate_of"))
        write_boilerplate(self.job_dir, blocks, pages)
        stats = self.crawler.stats.get_stats()
        status_counts = {
            key.rsplit("/", 1)[-1]: value
            for key, value in stats.items()
            if key.startswith("downloader/response_status_count/")
        }
        traps = getattr(spider, "traps", None)
        # What the owner sees: the job's pages and how much redundancy was marked or removed.
        result = {
            "pages": len(rows),
            "duplicates": sum(1 for row in rows if row.get("duplicate_of")),
            "near_duplicates": sum(1 for row in rows if row.get("near_duplicate_of")),
            "boilerplate_blocks": len(blocks),
            "trap_urls_skipped": sum(traps.skipped.values()) if traps else 0,
        }
        logger.info(
            "Result: %(pages)d pages, %(duplicates)d duplicates, %(near_duplicates)d near duplicates, "
            "%(boilerplate_blocks)d boilerplate blocks, %(trap_urls_skipped)d trap URLs skipped",
            result,
        )
        summary = {
            "seed_url": spider.start_urls[0],
            "allowed_hosts": spider.allowed_domains,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "finish_reason": reason,
            "pages_saved_this_run": self.saved,
            # Totals over every run of the job; trap URLs skipped by this run.
            "result": result,
            "requests_sent": stats.get("downloader/request_count", 0),
            "responses_by_status": status_counts,
            "request_errors": stats.get("downloader/exception_count", 0),
            # Trap URLs not requested, by rule, and large URL families worth a look.
            "skipped": dict(traps.skipped) if traps else {},
            "suspected_traps": traps.suspected() if traps else [],
            # The made-up address checked first, what it says about the site, and whether pages were rendered.
            **(spider.site_state() if hasattr(spider, "site_state") else {}),
            "results_file": "results.jsonl",
        }
        write_json(self.job_dir / "summary.json", summary)
