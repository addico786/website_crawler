import logging

from scrapy import signals
from scrapy.extensions.throttle import AutoThrottle

logger = logging.getLogger(__name__)


class ProgressExtension:
    """Log a small progress line every 25 server responses."""
    @classmethod
    def from_crawler(cls, crawler):
        extension = cls()
        crawler.signals.connect(extension.response_received, signal=signals.response_received)
        return extension

    def __init__(self):
        self.responses = 0

    def response_received(self, response, request, spider):
        self.responses += 1
        if self.responses % 25 == 0:
            spider.logger.info("Progress: %s responses received", self.responses)


class CrawlDelayExtension:
    """Honour robots.txt Crawl-delay, which Scrapy reads but does not apply.

    Delay = max(the user's delay, Crawl-delay), at most 60 s, set on the site's download slot
    and as AutoThrottle's minimum so AutoThrottle never speeds up past it.
    """
    MAX_DELAY = 60.0

    @classmethod
    def from_crawler(cls, crawler):
        extension = cls(crawler)
        crawler.signals.connect(extension.robots_parsed, signal=signals.robots_parsed)
        return extension

    def __init__(self, crawler):
        self.crawler = crawler
        self.user_agent = crawler.settings.get("ROBOTSTXT_USER_AGENT") or crawler.settings.get("USER_AGENT")

    def robots_parsed(self, robotparser, request):
        crawl_delay = robotparser.crawl_delay(self.user_agent)
        user_delay = self.crawler.settings.getfloat("DOWNLOAD_DELAY")
        if not crawl_delay or crawl_delay <= user_delay:
            return
        delay = min(float(crawl_delay), self.MAX_DELAY)
        downloader = self.crawler.engine.downloader
        slot = downloader.slots.get(downloader.get_slot_key(request))
        if slot is not None:
            # No jitter: a random -50% would go below the site's minimum.
            slot.delay, slot.jitter = max(slot.delay, delay), 0
        for extension in self.crawler.extensions.middlewares:
            if isinstance(extension, AutoThrottle):
                extension.mindelay = max(extension.mindelay, delay)
        logger.info(
            "robots.txt of %s asks for Crawl-delay: %g; waiting %.1f s between requests%s.",
            request.url.split("/")[2], crawl_delay, delay, " (capped)" if delay < crawl_delay else "",
        )
