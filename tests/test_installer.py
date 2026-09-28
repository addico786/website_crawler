import re
import zipfile
from pathlib import Path

import pytest

import server
import smoke_frozen

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "installer" / "WebsiteCrawler.iss").read_text(encoding="utf-8")


def setting(name):
    match = re.search(rf"^{name}=(.*)$", SCRIPT, re.M)
    return match and match.group(1)


def test_installer_installs_per_user_where_the_updater_can_write():
    assert setting("PrivilegesRequired") == "lowest"
    assert setting("DefaultDirName") == r"{localappdata}\Programs\WebsiteCrawler"
    assert "{pf}" not in SCRIPT and "{autopf}" not in SCRIPT and "{commonpf" not in SCRIPT
    assert re.fullmatch(r"\{\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}", setting("AppId"))  # fixed: upgrades in place
    assert setting("AppVersion") == "{#AppVersion}" and setting("CloseApplications") == "yes"
    assert setting("OutputBaseFilename") == "WebsiteCrawler-Setup"
    assert r'Name: "{autoprograms}\Website Crawler"' in SCRIPT
    assert 'Name: "desktopicon"' in SCRIPT and "unchecked" not in SCRIPT  # desktop shortcut, ticked
    assert 'Description: "Launch Website Crawler"; Flags: nowait postinstall skipifsilent' in SCRIPT


def test_uninstaller_asks_before_deleting_crawl_results():
    # The frozen app keeps jobs\ (and its logs) beside WebsiteCrawler.exe, that is in the install folder.
    assert server.JOBS_DIR == server.BASE_DIR / "jobs"
    assert "Path(sys.executable).parent if FROZEN" in (ROOT / "server.py").read_text(encoding="utf-8")
    assert r"ExpandConstant('{app}\jobs')" in SCRIPT and "Also delete your crawl results?" in SCRIPT
    assert "(not UninstallSilent) and (MsgBox(" in SCRIPT and "MB_DEFBUTTON2" in SCRIPT  # No is the default
    for leftover in (r"{app}\_internal", r"{app}\app.log", r"{app}\browser_install.log"):
        assert f'Name: "{leftover}"' in SCRIPT


def test_build_and_release_ship_the_installer():
    build = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
    assert r'"/DAppVersion=%APPVERSION%" installer\WebsiteCrawler.iss' in build
    # The version the build passes is server.VERSION.
    command = re.search(r'python" -c "(.*)" > build', build).group(1)
    assert re.search(re.search(r"r'(.*?)'", command).group(1), (ROOT / "server.py").read_text(encoding="utf-8"), re.M).group(1) == server.VERSION
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "choco install innosetup -y --no-progress" in release
    assert "            dist/WebsiteCrawler-Setup.exe\n            dist/WebsiteCrawler-windows.zip\n" in release
    assert "**Download `WebsiteCrawler-Setup.exe` below and double-click it.**" in release
    assert "unzip" not in release.lower() and "generate_release_notes: true" in release
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Download [`WebsiteCrawler-Setup.exe`](https://github.com/addico786/website_crawler/releases/latest) and double-click it.**" in readme
    assert "HOW TO INSTALL" not in readme and not (ROOT / "packaging").exists()


def fake_build(tmp_path, names):
    dist = tmp_path / "dist" / "WebsiteCrawler"
    dist.mkdir(parents=True)
    with zipfile.ZipFile(tmp_path / "dist" / "WebsiteCrawler-windows.zip", "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return dist


def test_frozen_smoke_checks_the_zip_layout(tmp_path, monkeypatch, capsys):
    complete = ["WebsiteCrawler/WebsiteCrawler.exe", "WebsiteCrawler/WebsiteCrawlerWorker.exe", "WebsiteCrawler/_internal/base_library.zip"]
    monkeypatch.setattr(smoke_frozen, "DIST", fake_build(tmp_path / "ok", complete))
    smoke_frozen.smoke_zip()
    assert "Zip OK" in capsys.readouterr().out

    monkeypatch.setattr(smoke_frozen, "DIST", fake_build(tmp_path / "missing", complete[1:]))
    with pytest.raises(SystemExit):
        smoke_frozen.smoke_zip()
    assert "WebsiteCrawler/WebsiteCrawler.exe is missing" in capsys.readouterr().out
