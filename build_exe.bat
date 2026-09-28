@echo off
REM Builds the Windows app: dist\WebsiteCrawler\WebsiteCrawler.exe, dist\WebsiteCrawler-windows.zip
REM (what the in-app updater installs) and, with Inno Setup 6, dist\WebsiteCrawler-Setup.exe (for new users).
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

REM The installer, dist\WebsiteCrawler-Setup.exe, when Inno Setup 6 is installed (release.yml installs it).
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do set "ISCC=%%i"
if not exist "%ISCC%" (
  echo Inno Setup 6 not found: no installer built.
  exit /b 0
)
".venv-win\Scripts\python" -c "import re; print(re.search(r'^VERSION = .([0-9.]+)', open('server.py', encoding='utf-8').read(), re.M).group(1))" > build\appversion.txt || exit /b 1
set /p APPVERSION=<build\appversion.txt
"%ISCC%" /Q "/DAppVersion=%APPVERSION%" installer\WebsiteCrawler.iss || exit /b 1
echo Built dist\WebsiteCrawler-Setup.exe (version %APPVERSION%)
