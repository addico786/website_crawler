import asyncio
import ctypes
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

VERSION = "1.0.0"  # Bump before tagging a release; the tag must be v<VERSION>.
UPDATE_REPO = "addico786/website_crawler"  # GitHub repo whose Releases hold the Windows builds; must be public.
# Override to test the updater against a local fake release.
UPDATE_URL = os.environ.get("CRAWLER_UPDATE_URL", f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest")

# Base Directory & Paths. In the packaged .exe (PyInstaller), bundled files live in
# sys._MEIPASS while jobs/ sits next to the .exe so it survives updates.
FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent.resolve()
JOBS_DIR = BASE_DIR / "jobs"
STATIC_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "static"
# The .exe re-launches itself with --crawl (see app.py); from source we run crawl.py.
CRAWL_CMD = [sys.executable, "--crawl"] if FROZEN else [sys.executable, str(BASE_DIR / "crawl.py")]

JOBS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Website Crawler Dashboard API",
    description="Backend API for managing Scrapy web crawler jobs, monitoring progress, and viewing results.",
    version=VERSION,
)

# Active Process Tracker: job_id -> Popen process object
active_processes: Dict[str, subprocess.Popen] = {}


class StartJobRequest(BaseModel):
    url: str
    job_name: Optional[str] = None
    preset: Optional[str] = "quick"  # quick, deep, custom
    max_pages: int = Field(default=100, ge=1, le=50000)
    max_depth: int = Field(default=3, ge=1, le=50)
    minutes: float = Field(default=5.0, ge=0.0, le=1440.0)
    delay: float = Field(default=1.0, ge=0.0, le=60.0)
    concurrency: int = Field(default=1, ge=1, le=16)
    use_sitemap: bool = True
    render_js: bool = False


def sanitize_job_name(url: str, custom_name: Optional[str] = None) -> str:
    if custom_name and custom_name.strip():
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", custom_name.strip())
        return clean.lower()
    
    # Auto-generate from URL
    clean_url = re.sub(r"^https?://", "", url.lower())
    clean_url = re.sub(r"[^a-zA-Z0-9]", "_", clean_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{clean_url[:30]}_{timestamp}"


def get_job_path(job_id: str) -> Path:
    # Reject "..", "%2E%2E" and friends so no endpoint can reach outside jobs/.
    path = (JOBS_DIR / job_id).resolve()
    if path.parent != JOBS_DIR:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return path


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h != 0:
                exit_code = ctypes.c_ulong()
                STILL_ACTIVE = 259
                is_active = True
                if ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code)):
                    is_active = (exit_code.value == STILL_ACTIVE)
                ctypes.windll.kernel32.CloseHandle(h)
                return is_active
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def kill_process_tree(pid: int):
    if pid <= 0:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        else:
            try:
                import signal
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass
    except Exception:
        pass


def safe_remove_job_dir(job_path: Path, max_attempts: int = 8) -> bool:
    if not job_path.exists():
        return True

    def remove_readonly(func, path, exc):
        try:
            os.chmod(path, 0o777)
            func(path)
        except Exception:
            pass

    for _ in range(max_attempts):
        try:
            shutil.rmtree(job_path, onerror=remove_readonly)
            if not job_path.exists():
                return True
        except Exception:
            time.sleep(0.15)

    if job_path.exists():
        try:
            shutil.rmtree(job_path, ignore_errors=True)
        except Exception:
            pass

    return not job_path.exists()


def is_job_running(job_id: str) -> bool:
    exit_code = None
    proc = active_processes.get(job_id)
    if proc is not None:
        if proc.poll() is None:
            return True
        exit_code = proc.returncode
        del active_processes[job_id]

    pid_file = get_job_path(job_id) / "pid.json"
    if pid_file.exists():
        try:
            data = json.loads(pid_file.read_text(encoding="utf-8"))
            if data.get("status") == "running":
                pid = data.get("pid")
                if pid and pid_exists(pid):
                    return True
                else:
                    data["status"] = "failed" if exit_code else "completed"
                    pid_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
    return False


def get_job_status(job_id: str) -> str:
    job_path = get_job_path(job_id)
    if not job_path.exists():
        return "not_found"

    if is_job_running(job_id):
        return "running"

    pid_file = job_path / "pid.json"
    if pid_file.exists():
        try:
            pid_data = json.loads(pid_file.read_text(encoding="utf-8"))
            if pid_data.get("status") in ["stopped", "completed", "failed"]:
                return pid_data["status"]
        except Exception:
            pass

    summary_file = job_path / "summary.json"
    if summary_file.exists():
        return "completed"

    results_file = job_path / "results.jsonl"
    if results_file.exists():
        return "completed"

    log_file = job_path / "job.log"
    if log_file.exists():
        log_content = log_file.read_text(encoding="utf-8", errors="ignore")
        if "Spider closed" in log_content:
            return "completed"
        elif "Traceback" in log_content or "Error" in log_content:
            return "failed"

    return "idle"


@app.post("/api/jobs/start")
def start_crawl_job(req: StartJobRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    job_id = sanitize_job_name(url, req.job_name)
    job_dir = get_job_path(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    if is_job_running(job_id):
        raise HTTPException(status_code=400, detail=f"Job '{job_id}' is already running.")

    # Build crawl.py command
    cmd = [
        *CRAWL_CMD,
        url,
        "--minutes", str(req.minutes),
        "--job", str(job_dir.resolve()),
        "--delay", str(req.delay),
        "--concurrency", str(req.concurrency),
        "--max-pages", str(req.max_pages),
        "--max-depth", str(req.max_depth),
    ]
    if not req.use_sitemap:
        cmd.append("--no-sitemap")
    if req.render_js:
        cmd.append("--render-js")

    log_file_path = job_dir / "job.log"
    log_file = open(log_file_path, "a", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            # Own process group, so killpg() on stop doesn't take the server down with it.
            start_new_session=sys.platform != "win32",
        )
        active_processes[job_id] = proc

        # Write pid metadata
        pid_data = {
            "pid": proc.pid,
            "job_id": job_id,
            "seed_url": url,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "params": req.model_dump(),
        }
        (job_dir / "pid.json").write_text(json.dumps(pid_data, indent=2), encoding="utf-8")

        return {
            "status": "success",
            "job_id": job_id,
            "message": f"Crawl job '{job_id}' started successfully.",
            "params": pid_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crawler process: {str(e)}")


@app.post("/api/jobs/{job_id}/stop")
def stop_crawl_job(job_id: str):
    job_path = get_job_path(job_id)
    if not job_path.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    proc = active_processes.get(job_id)
    if proc is not None:
        kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        del active_processes[job_id]

    pid_file = job_path / "pid.json"
    if pid_file.exists():
        try:
            pid_data = json.loads(pid_file.read_text(encoding="utf-8"))
            pid = pid_data.get("pid")
            # Old jobs' PIDs may since belong to unrelated processes.
            if pid and pid_data.get("status") == "running" and pid_exists(pid):
                kill_process_tree(pid)
            pid_data["status"] = "stopped"
            pid_data["stopped_at"] = datetime.now(timezone.utc).isoformat()
            pid_file.write_text(json.dumps(pid_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    return {"status": "success", "message": f"Job '{job_id}' stopped."}


@app.delete("/api/jobs/{job_id}")
def delete_crawl_job(job_id: str):
    job_path = get_job_path(job_id)
    if not job_path.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    # 1. Terminate tracked subprocess and entire process tree
    proc = active_processes.get(job_id)
    if proc is not None:
        kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        del active_processes[job_id]

    # 2. Terminate PID from pid.json process tree
    pid_file = job_path / "pid.json"
    if pid_file.exists():
        try:
            pid_data = json.loads(pid_file.read_text(encoding="utf-8"))
            pid = pid_data.get("pid")
            # Old jobs' PIDs may since belong to unrelated processes.
            if pid and pid_data.get("status") == "running" and pid_exists(pid):
                kill_process_tree(pid)
        except Exception:
            pass

    # 3. Brief pause for OS file handle releases
    time.sleep(0.15)

    # 4. Safely and completely delete job directory
    deleted = safe_remove_job_dir(job_path)
    if not deleted:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete job '{job_id}'. A file may still be locked by the operating system. Please try again in a moment.",
        )

    return {"status": "success", "message": f"Job '{job_id}' and all associated files deleted successfully."}



@app.get("/api/jobs")
def list_jobs():
    jobs = []
    if not JOBS_DIR.exists():
        return {"jobs": []}

    for item in sorted(JOBS_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
        if not item.is_dir():
            continue

        job_id = item.name
        status = get_job_status(job_id)
        
        # Read summary or pid file if available
        summary_file = item / "summary.json"
        pid_file = item / "pid.json"
        results_file = item / "results.jsonl"

        seed_url = "N/A"
        started_at = None
        pages_saved = 0
        requests_sent = 0
        request_errors = 0

        if results_file.exists():
            try:
                with open(results_file, "r", encoding="utf-8") as f:
                    pages_saved = sum(1 for line in f if line.strip())
            except Exception:
                pass

        if summary_file.exists():
            try:
                sdata = json.loads(summary_file.read_text(encoding="utf-8"))
                seed_url = sdata.get("seed_url", seed_url)
                started_at = sdata.get("started_at", started_at)
                requests_sent = sdata.get("requests_sent", requests_sent)
                request_errors = sdata.get("request_errors", request_errors)
            except Exception:
                pass

        render_js = False
        if pid_file.exists():
            try:
                pdata = json.loads(pid_file.read_text(encoding="utf-8"))
                if seed_url == "N/A":
                    seed_url = pdata.get("seed_url", seed_url)
                    started_at = pdata.get("started_at", started_at)
                render_js = pdata.get("params", {}).get("render_js", False)
            except Exception:
                pass

        jobs.append({
            "job_id": job_id,
            "seed_url": seed_url,
            "status": status,
            "started_at": started_at or datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat(),
            "pages_saved": pages_saved,
            "requests_sent": requests_sent,
            "request_errors": request_errors,
            "render_js": render_js,
        })

    return {"jobs": jobs}


@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str):
    job_path = get_job_path(job_id)
    if not job_path.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    status = get_job_status(job_id)
    summary_file = job_path / "summary.json"
    pid_file = job_path / "pid.json"
    results_file = job_path / "results.jsonl"
    log_file = job_path / "job.log"

    summary_data = {}
    if summary_file.exists():
        try:
            summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pid_data = {}
    if pid_file.exists():
        try:
            pid_data = json.loads(pid_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pages_saved = 0
    total_words = 0
    total_links = 0
    if results_file.exists():
        try:
            with open(results_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    pages_saved += 1
                    total_words += item.get("word_count", 0)
                    total_links += item.get("links_found", 0)
        except Exception:
            pass

    recent_logs = ""
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            recent_logs = "\n".join(lines[-100:])
        except Exception:
            pass

    return {
        "job_id": job_id,
        "status": status,
        "seed_url": summary_data.get("seed_url") or pid_data.get("seed_url", "N/A"),
        "pages_saved": pages_saved,
        "total_words": total_words,
        "total_links": total_links,
        "summary": summary_data,
        "pid_info": pid_data,
        "render_js": pid_data.get("params", {}).get("render_js", False),
        "recent_logs": recent_logs,
    }


@app.get("/api/jobs/{job_id}/results")
def get_job_results(
    job_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=500),
    search: str = Query(default=""),
    status_code: Optional[int] = Query(default=None),
):
    job_path = get_job_path(job_id)
    results_file = job_path / "results.jsonl"
    if not results_file.exists():
        return {"items": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

    search_query = search.strip().lower()
    matched_items = []

    try:
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                
                # Apply status_code filter
                if status_code is not None and item.get("status") != status_code:
                    continue

                # Apply search filter
                if search_query:
                    url = item.get("url", "").lower()
                    title = item.get("title", "").lower()
                    desc = item.get("description", "").lower()
                    text = item.get("text", "").lower()
                    headings = " ".join(item.get("headings", [])).lower()

                    if (
                        search_query not in url
                        and search_query not in title
                        and search_query not in desc
                        and search_query not in text
                        and search_query not in headings
                    ):
                        continue

                matched_items.append(item)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading job results: {str(e)}")

    total = len(matched_items)
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paged_items = matched_items[start_idx:end_idx]

    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }


@app.get("/api/jobs/{job_id}/logs")
async def stream_job_logs(job_id: str, request: Request):
    job_path = get_job_path(job_id)
    log_file = job_path / "job.log"
    if not log_file.exists():
        return Response(content="Log file not found.", media_type="text/plain")

    async def event_stream():
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                while True:
                    if await request.is_disconnected():
                        break
                    line = f.readline()
                    if line:
                        yield f"data: {json.dumps({'line': line.strip()})}\n\n"
                    else:
                        if not is_job_running(job_id):
                            remaining = f.read()
                            if remaining:
                                for l in remaining.splitlines():
                                    yield f"data: {json.dumps({'line': l.strip()})}\n\n"
                            yield f"data: {json.dumps({'done': True})}\n\n"
                            break
                        await asyncio.sleep(0.5)
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception:
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/export")
def export_job_results(job_id: str, format: str = Query(default="csv")):
    job_path = get_job_path(job_id)
    results_file = job_path / "results.jsonl"
    if not results_file.exists():
        raise HTTPException(status_code=404, detail=f"No results found for job '{job_id}'.")

    items = []
    try:
        with open(results_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read results: {str(e)}")

    if format.lower() == "json":
        json_content = json.dumps(items, indent=2, ensure_ascii=False)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={job_id}_results.json"},
        )

    # CSV Format Default
    output = io.StringIO()
    fieldnames = [
        "url",
        "status",
        "title",
        "description",
        "word_count",
        "links_found",
        "canonical_url",
        "headings",
        "crawled_at",
        "found_on",
        "text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for item in items:
        row = dict(item)
        if isinstance(row.get("headings"), list):
            row["headings"] = " | ".join(row["headings"])
        writer.writerow(row)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={job_id}_results.csv"},
    )


@app.get("/api/stats/overview")
def get_global_stats():
    total_jobs = 0
    active_jobs = 0
    total_pages = 0
    total_words = 0
    total_links = 0

    if JOBS_DIR.exists():
        for item in JOBS_DIR.iterdir():
            if item.is_dir():
                total_jobs += 1
                job_id = item.name
                if is_job_running(job_id):
                    active_jobs += 1

                results_file = item / "results.jsonl"
                if results_file.exists():
                    try:
                        with open(results_file, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    data = json.loads(line)
                                    total_pages += 1
                                    total_words += data.get("word_count", 0)
                                    total_links += data.get("links_found", 0)
                    except Exception:
                        pass

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "total_pages": total_pages,
        "total_words": total_words,
        "total_links": total_links,
    }


def parse_version(tag: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", tag)[:3])


def fetch_latest_release() -> dict:
    request = urllib.request.Request(
        UPDATE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"WebsiteCrawler/{VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


@app.get("/api/version")
def get_version():
    return {"version": VERSION, "can_self_update": FROZEN and sys.platform == "win32"}


@app.get("/api/update/check")
def check_for_update():
    try:
        release = fetch_latest_release()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(status_code=502, detail="No published releases found, or the update repository is private.")
        raise HTTPException(status_code=502, detail=f"GitHub returned HTTP {e.code}.")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {e}")

    latest = release.get("tag_name", "").lstrip("v")
    zips = [a["browser_download_url"] for a in release.get("assets", []) if a.get("name", "").endswith(".zip")]
    return {
        "current_version": VERSION,
        "latest_version": latest,
        "update_available": parse_version(latest) > parse_version(VERSION),
        "release_url": release.get("html_url"),
        "download_url": zips[0] if zips else None,
        "notes": release.get("body") or "",
        "can_self_update": get_version()["can_self_update"],
    }


@app.post("/api/update/install")
def install_update():
    if not get_version()["can_self_update"]:
        raise HTTPException(status_code=400, detail="Self-update only works in the Windows app. From source, use git pull.")
    # Crawls run from the same .exe files the update replaces.
    if any(is_job_running(item.name) for item in JOBS_DIR.iterdir() if item.is_dir()):
        raise HTTPException(status_code=409, detail="Stop running crawls before updating.")
    info = check_for_update()
    if not info["update_available"] or not info["download_url"]:
        raise HTTPException(status_code=400, detail="No downloadable update available.")

    staging = BASE_DIR / "_update"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    archive = staging / "update.zip"
    try:
        request = urllib.request.Request(info["download_url"], headers={"User-Agent": f"WebsiteCrawler/{VERSION}"})
        with urllib.request.urlopen(request, timeout=300) as response, open(archive, "wb") as out:
            shutil.copyfileobj(response, out)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging / "new")
    except Exception as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(status_code=502, detail=f"Failed to download update: {e}")

    exe = Path(sys.executable)
    found = list((staging / "new").rglob(exe.name))
    if not found:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(status_code=502, detail=f"Update package has no {exe.name}.")
    new_dir = found[0].parent

    # A running .exe can't overwrite itself: hand off to a script that waits for this
    # process to exit, swaps the files (jobs/ is left alone), and starts the new version.
    # Anything else running from the app folder (the background Chromium installer and its
    # node.exe) would lock _internal, so it is stopped too. (`timeout` needs a console; none here.)
    app_dir = str(BASE_DIR).replace("'", "''") + "\\"  # quoted for PowerShell
    script = staging / "apply_update.bat"
    script.write_text(
        "@echo off\r\n"
        f'powershell -NoProfile -Command "Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; '
        f"Get-Process | Where-Object {{ $_.Path -and $_.Path.StartsWith('{app_dir}', 'OrdinalIgnoreCase') }} | Stop-Process -Force; Start-Sleep 1\"\r\n"
        f'robocopy "{new_dir / "_internal"}" "{BASE_DIR / "_internal"}" /MIR /R:5 /W:1 >nul\r\n'
        f'copy /y "{new_dir / exe.name}" "{exe}" >nul\r\n'
        f'start "" "{exe}" --no-browser\r\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    threading.Timer(1.0, os._exit, [0]).start()  # let this response reach the browser first
    return {"status": "success", "message": f"Installing v{info['latest_version']}; the dashboard will restart."}


# Mount Static Dashboard Frontend
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"[+] Starting Website Crawler Dashboard at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
