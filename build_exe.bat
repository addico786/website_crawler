@echo off
REM Builds the Windows app: dist\WebsiteCrawler\WebsiteCrawler.exe
REM and dist\WebsiteCrawler-windows.zip (the file to attach to a GitHub Release).
REM Must run on Windows: PyInstaller cannot cross-compile.
setlocal
cd /d "%~dp0"

if not exist ".venv-win\Scripts\python.exe" python -m venv .venv-win || exit /b 1
".venv-win\Scripts\python" -m pip install -q -r requirements.txt pyinstaller || exit /b 1

REM Scrapy, scrapy-playwright and uvicorn load many modules by name, so collect them explicitly;
REM --copy-metadata covers packages whose version Scrapy / scrapy-playwright log at start-up.
REM polite_crawler modules are listed one by one: --collect-submodules silently finds nothing for
REM a local package. Add new spiders/pipelines/extensions here. Spider .py source is bundled too:
REM Scrapy calls inspect.getsource() on spider callbacks, which fails on bytecode alone.
".venv-win\Scripts\pyinstaller" --noconfirm --clean --onedir --name WebsiteCrawler ^
  --add-data "static;static" ^
  --add-data "polite_crawler\spiders\*.py;polite_crawler\spiders" ^
  --collect-all scrapy ^
  --hidden-import polite_crawler.settings ^
  --hidden-import polite_crawler.spiders.site ^
  --hidden-import polite_crawler.pipelines ^
  --hidden-import polite_crawler.extensions ^
  --collect-submodules scrapy_playwright ^
  --collect-submodules uvicorn ^
  --collect-data tldextract ^
  --hidden-import twisted.internet.asyncioreactor ^
  --copy-metadata lxml ^
  --copy-metadata cssselect ^
  --copy-metadata parsel ^
  --copy-metadata w3lib ^
  --copy-metadata Twisted ^
  --copy-metadata cryptography ^
  --copy-metadata scrapy-playwright ^
  --copy-metadata playwright ^
  app.py || exit /b 1

REM Python's zip, not Compress-Archive: that one reports failures with exit code 0.
".venv-win\Scripts\python" -c "import shutil; shutil.make_archive('dist/WebsiteCrawler-windows', 'zip', 'dist', 'WebsiteCrawler')" || exit /b 1
echo.
echo Built dist\WebsiteCrawler\WebsiteCrawler.exe and dist\WebsiteCrawler-windows.zip
