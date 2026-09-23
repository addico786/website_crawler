BOT_NAME = "polite_crawler"
SPIDER_MODULES = ["polite_crawler.spiders"]
NEWSPIDER_MODULE = "polite_crawler.spiders"

# Compliance and long-running safety defaults. Override deliberately via crawl.py.
ROBOTSTXT_OBEY = True
USER_AGENT = "PoliteCrawler/1.0 (+https://example.invalid/crawler-contact)"
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 60.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1.0
DOWNLOAD_DELAY_JITTER = 0.5
DOWNLOAD_TIMEOUT = 30
RETRY_TIMES = 2
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504]
# Pass 4xx/5xx pages to the spider (after retries) so the dashboard status filter has something to show.
HTTPERROR_ALLOW_ALL = True
HTTPCACHE_ENABLED = False
ITEM_PIPELINES = {"polite_crawler.pipelines.JobOutputPipeline": 300}
EXTENSIONS = {
    "polite_crawler.extensions.ProgressExtension": 500,
    "scrapy.extensions.telnet.TelnetConsole": None,
    "scrapy.extensions.remote_control.RemoteControl": None,
}
LOG_LEVEL = "INFO"

# Optional JS-rendering with Playwright
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
}
