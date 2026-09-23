"""Entry point for the packaged Windows app (built by build_exe.bat).

The .exe has no python.exe beside it, so it re-launches itself with a flag for
work that normally runs as a separate Python process.
"""
import os
import shutil
import subprocess
import sys
import threading
import webbrowser


def main():
    # Frozen, Playwright looks for browsers inside the bundle (replaced by every update)
    # while `playwright install` uses the per-user folder. Point both at the latter.
    if getattr(sys, "frozen", False) and os.name == "nt":
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright"))

    if sys.argv[1:2] == ["--crawl"]:  # started by server.py for each crawl
        import crawl
        del sys.argv[1]
        return crawl.main()

    if sys.argv[1:2] == ["--install-browser"]:  # Chromium for "Render JavaScript" crawls
        from playwright.__main__ import main as playwright_main
        sys.argv = ["playwright", "install", "chromium"]
        return playwright_main()

    import server
    import uvicorn

    shutil.rmtree(server.BASE_DIR / "_update", ignore_errors=True)  # leftovers from the last update
    if server.FROZEN:
        # Idempotent and quick once Chromium is present; downloads ~150 MB the first time.
        with open(server.BASE_DIR / "browser_install.log", "w", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, "--install-browser"], stdout=log, stderr=subprocess.STDOUT)

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Website Crawler v{server.VERSION} running at http://localhost:{port}")
    print("Keep this window open while you use the dashboard. Close it to stop.")
    if "--no-browser" not in sys.argv:  # the updater restarts us; the open tab reloads itself
        threading.Timer(1.5, webbrowser.open, [f"http://localhost:{port}"]).start()
    uvicorn.run(server.app, host=host, port=port)


if __name__ == "__main__":
    raise SystemExit(main())
