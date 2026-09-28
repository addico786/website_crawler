import zipfile
from pathlib import Path

import pytest

import server
import smoke_frozen

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "packaging" / "HOW TO INSTALL.txt"


def test_install_notes_say_what_the_app_does():
    notes = NOTES.read_text(encoding="utf-8")
    for step in ("Do not run it from inside the zip", "WebsiteCrawler.exe", '"More info", then "Run anyway"',
                 "Check for Updates", "Do not unzip a new version over", r"%LOCALAPPDATA%\ms-playwright"):
        assert step in notes
    # The notes say results are in "jobs" next to WebsiteCrawler.exe: that is where the frozen app keeps them.
    assert '"jobs" folder inside the WebsiteCrawler folder' in notes
    assert server.JOBS_DIR == server.BASE_DIR / "jobs"
    assert "Path(sys.executable).parent if FROZEN" in (ROOT / "server.py").read_text(encoding="utf-8")
    # The build puts them beside the .exe files, and the release page says which file to download.
    assert 'Path(SPECPATH) / "packaging" / "HOW TO INSTALL.txt"' in (ROOT / "WebsiteCrawler.spec").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert '**Download `WebsiteCrawler-windows.zip` below** (not "Source code")' in release
    assert "generate_release_notes: true" in release


def fake_build(tmp_path, names):
    dist = tmp_path / "dist" / "WebsiteCrawler"
    dist.mkdir(parents=True)
    with zipfile.ZipFile(tmp_path / "dist" / "WebsiteCrawler-windows.zip", "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return dist


def test_frozen_smoke_checks_the_zip(tmp_path, monkeypatch, capsys):
    complete = ["WebsiteCrawler/WebsiteCrawler.exe", "WebsiteCrawler/WebsiteCrawlerWorker.exe",
                "WebsiteCrawler/HOW TO INSTALL.txt", "WebsiteCrawler/_internal/base_library.zip"]
    monkeypatch.setattr(smoke_frozen, "DIST", fake_build(tmp_path / "ok", complete))
    smoke_frozen.smoke_zip()
    assert "Zip OK" in capsys.readouterr().out

    monkeypatch.setattr(smoke_frozen, "DIST", fake_build(tmp_path / "missing", complete[:2]))
    with pytest.raises(SystemExit):
        smoke_frozen.smoke_zip()
    assert "WebsiteCrawler/HOW TO INSTALL.txt is missing" in capsys.readouterr().out
