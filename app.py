"""Entry point for the packaged Windows app (built by build_exe.bat / WebsiteCrawler.spec).

WebsiteCrawler.exe shows the dashboard in its own window (pywebview + Edge WebView2).
Work that normally runs as a separate Python process is done by relaunching this same
program with a flag, as WebsiteCrawlerWorker.exe (its console twin; see server.WORKER_EXE).
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request


def dashboard_running(url):
    try:
        urllib.request.urlopen(url + "/api/version", timeout=1)
        return True
    except OSError:
        return False


def show_window(url):
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True  # CSV/JSON export
    webview.create_window("Website Crawler", url, width=1400, height=900, min_size=(960, 640))
    webview.start()  # blocks until the window is closed


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

    if sys.stdout is None:  # windowed .exe has no console, and uvicorn's logging needs a stream
        sys.stdout = sys.stderr = open(server.BASE_DIR / "app.log", "w", encoding="utf-8", buffering=1)

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    url = f"http://127.0.0.1:{port}"

    if dashboard_running(url):  # opened twice: another window onto the running app
        show_window(url)
        return 0

    shutil.rmtree(server.BASE_DIR / "_update", ignore_errors=True)  # leftovers from the last update
    if server.FROZEN:
        # Idempotent and quick once Chromium is present; downloads ~150 MB the first time.
        with open(server.BASE_DIR / "browser_install.log", "w", encoding="utf-8") as log:
            subprocess.Popen(
                [str(server.WORKER_EXE), "--install-browser"],
                stdout=log, stderr=subprocess.STDOUT, creationflags=server.NO_WINDOW,
            )

    if "--server-only" in sys.argv:  # no window; used by tests
        uvicorn.run(server.app, host=host, port=port)
        return 0

    srv = uvicorn.Server(uvicorn.Config(server.app, host=host, port=port))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started and thread.is_alive():
        time.sleep(0.1)
    if not srv.started:
        message = f"Could not start the dashboard: port {port} is in use by another program."
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Website Crawler", 0x10)
        print(message)
        return 1

    show_window(url)
    server.stop_all_crawls()  # closing the app stops its crawls, as closing the old console window did
    srv.should_exit = True
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
