#!/usr/bin/env python3
"""Run or resume one polite, same-site Scrapy crawl."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from scrapy.cmdline import execute


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Seed URL, e.g. https://example.com")
    parser.add_argument("--minutes", type=float, default=60, help="0 means run until complete or Ctrl-C")
    parser.add_argument("--job", default=None, help="Persistent job directory (re-use to resume)")
    parser.add_argument("--delay", type=float, default=1.0, help="Minimum seconds between requests per host")
    parser.add_argument("--concurrency", type=int, default=1, help="Max simultaneous requests per host")
    parser.add_argument("--max-pages", type=int, default=1000, help="Safety cap on saved pages (0 means no cap)")
    parser.add_argument("--max-depth", type=int, default=8, help="How many links deep to follow (0 means no cap)")
    parser.add_argument("--no-sitemap", action="store_true", help="Do not also check /sitemap.xml")
    parser.add_argument("--render-js", action="store_true", help="Enable JavaScript rendering with Playwright for dynamic/SPA pages")
    args = parser.parse_args()

    host = urlparse(args.url).hostname
    if not host or urlparse(args.url).scheme not in {"http", "https"}:
        parser.error("url must be an http(s) URL")
    if args.delay < 0 or args.concurrency < 1 or args.max_pages < 0 or args.max_depth < 0:
        parser.error("delay and limits cannot be negative; concurrency must be at least 1")
    job = Path(args.job or f"jobs/{host.replace('.', '_')}")
    job.mkdir(parents=True, exist_ok=True)
    command = [
        "scrapy", "crawl", "site", "-a", f"start_url={args.url}",
        "-a", f"job_dir={job.resolve()}", "-a", f"use_sitemap={not args.no_sitemap}",
        "-a", f"render_js={args.render_js}",
        "-s", f"JOBDIR={job.resolve()}", "-s", f"DOWNLOAD_DELAY={args.delay}",
        "-s", f"CONCURRENT_REQUESTS_PER_DOMAIN={args.concurrency}",
    ]
    if args.max_pages:
        command += ["-s", f"CLOSESPIDER_ITEMCOUNT={args.max_pages}"]
    if args.max_depth:
        command += ["-s", f"DEPTH_LIMIT={args.max_depth}"]
    if args.minutes > 0:
        command += ["-s", f"CLOSESPIDER_TIMEOUT={args.minutes * 60}"]
    # Run Scrapy in this process rather than via `python -m scrapy`: the packaged
    # .exe has no separate python.exe to hand the crawl to. execute() exits the process.
    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "polite_crawler.settings")
    execute(command)


if __name__ == "__main__":
    raise SystemExit(main())
