"""Downloader middleware: wait as long as the server asks after 429 Too Many Requests / 503."""
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def retry_after_seconds(value):
    """Retry-After is either a number of seconds or an HTTP date; None when unreadable."""
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class RetryAfterMiddleware:
    """Scrapy's RetryMiddleware (550) retries 429/503 but ignores Retry-After. Running just
    before it (560), this sets the site's download slot to wait that long, at most 10 minutes."""
    MAX_WAIT = 600.0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        self.crawler = crawler

    def process_response(self, request, response, spider=None):
        header = response.headers.get(b"Retry-After")
        if response.status not in (429, 503) or not header:
            return response
        seconds = retry_after_seconds(header.decode("latin-1"))
        if not seconds:
            return response
        wait = min(seconds, self.MAX_WAIT)
        downloader = self.crawler.engine.downloader
        slot = downloader.slots.get(downloader.get_slot_key(request))
        if slot is not None:
            # No jitter: a random -50% would send the next request before the server asked.
            slot.delay, slot.jitter = max(slot.delay, wait), 0
        logger.info(
            "%s answered %s with Retry-After: %s; waiting %.0f s before the next request to that site.",
            request.url, response.status, header.decode("latin-1"), wait,
        )
        return response
