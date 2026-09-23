@echo off
REM Builds the Windows app: dist\WebsiteCrawler\WebsiteCrawler.exe
REM and dist\WebsiteCrawler-windows.zip (the file to attach to a GitHub Release).
REM Must run on Windows: PyInstaller cannot cross-compile. Build details: WebsiteCrawler.spec
setlocal
cd /d "%~dp0"

if not exist ".venv-win\Scripts\python.exe" python -m venv .venv-win || exit /b 1
".venv-win\Scripts\python" -m pip install -q -r requirements.txt pyinstaller || exit /b 1
".venv-win\Scripts\pyinstaller" --noconfirm --clean WebsiteCrawler.spec || exit /b 1

REM Python's zip, not Compress-Archive: that one reports failures with exit code 0.
".venv-win\Scripts\python" -c "import shutil; shutil.make_archive('dist/WebsiteCrawler-windows', 'zip', 'dist', 'WebsiteCrawler')" || exit /b 1
echo.
echo Built dist\WebsiteCrawler\WebsiteCrawler.exe and dist\WebsiteCrawler-windows.zip
