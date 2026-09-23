from scrapy import signals


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
