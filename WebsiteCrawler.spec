# PyInstaller build of the Windows app. Run build_exe.bat (PyInstaller can't cross-compile).
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas = [
    ("static", "static"),
    # Scrapy calls inspect.getsource() on spider callbacks, which fails on bytecode alone.
    ("polite_crawler/spiders/*.py", "polite_crawler/spiders"),
    *collect_data_files("tldextract"),
]
# Scrapy, scrapy-playwright and uvicorn load many modules by name. polite_crawler is listed
# module by module: collect_submodules() silently finds nothing for a local package.
hiddenimports = [
    "polite_crawler.settings",
    "polite_crawler.spiders.site",
    "polite_crawler.pipelines",
    "polite_crawler.extensions",
    "twisted.internet.asyncioreactor",
    *collect_submodules("scrapy_playwright"),
    *collect_submodules("uvicorn"),
]
scrapy_datas, binaries, scrapy_hidden = collect_all("scrapy")
datas += scrapy_datas
hiddenimports += scrapy_hidden
# Packages whose version Scrapy / scrapy-playwright log at start-up.
for package in ["lxml", "cssselect", "parsel", "w3lib", "Twisted", "cryptography", "scrapy-playwright", "playwright"]:
    datas += copy_metadata(package)

a = Analysis(["app.py"], datas=datas, binaries=binaries, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)

# The same program twice: WebsiteCrawler.exe is the window people open; the console twin
# runs crawls hidden, so the node/Chromium processes it starts don't pop up console windows.
app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WebsiteCrawler", console=False)
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name="WebsiteCrawlerWorker", console=True)
coll = COLLECT(app, worker, a.binaries, a.datas, name="WebsiteCrawler")
