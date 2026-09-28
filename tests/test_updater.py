import hashlib
import io
import zipfile
from functools import partial

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import server
from conftest import QuietHandler, serve

client = TestClient(server.app, base_url="http://127.0.0.1:8000")


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.fixture
def release_files(tmp_path):
    """A folder served on 127.0.0.1, standing in for GitHub's release downloads."""
    folder = tmp_path / "files"
    folder.mkdir()
    site = serve(partial(QuietHandler, directory=str(folder)))
    yield folder, f"http://127.0.0.1:{site.server_port}"
    site.shutdown()


def fake_release(monkeypatch, assets):
    release = {"tag_name": "v99.0.0", "html_url": "https://github.com/x/y/releases/tag/v99.0.0", "assets": assets}
    monkeypatch.setattr(server, "fetch_latest_release", lambda: release)


def test_update_asset_is_picked_by_name_and_needs_a_digest(monkeypatch):
    other = {"name": "Source.zip", "browser_download_url": "https://example.com/source.zip", "digest": "sha256:" + "a" * 64}
    ours = {"name": server.UPDATE_ASSET, "browser_download_url": "https://example.com/app.zip", "digest": "sha256:" + "B" * 64}
    fake_release(monkeypatch, [other, ours])
    data = client.get("/api/update/check").json()
    assert data["download_url"] == "https://example.com/app.zip" and data["sha256"] == "b" * 64

    # No digest published: offer the release page only (download_url null), and refuse to install.
    fake_release(monkeypatch, [{**ours, "digest": None}])
    data = client.get("/api/update/check").json()
    assert data["update_available"] and data["download_url"] is None
    assert data["release_url"].endswith("v99.0.0")
    monkeypatch.setattr(server, "FROZEN", True)
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "is_job_running", lambda job_id: False)
    assert client.post("/api/update/install", json={}).status_code == 400


def test_download_update_checks_sha256(release_files, tmp_path):
    folder, base = release_files
    package = make_zip({"WebsiteCrawler/WebsiteCrawler.exe": b"new exe", "WebsiteCrawler/_internal/a.txt": b"x"})
    (folder / server.UPDATE_ASSET).write_bytes(package)
    url = f"{base}/{server.UPDATE_ASSET}"
    staging = tmp_path / "_update"

    new_dir = server.download_update(url, hashlib.sha256(package).hexdigest(), staging, "WebsiteCrawler.exe")
    assert (new_dir / "WebsiteCrawler.exe").read_bytes() == b"new exe"
    assert (new_dir / "_internal" / "a.txt").exists()

    with pytest.raises(HTTPException) as error:
        server.download_update(url, hashlib.sha256(b"something else").hexdigest(), staging, "WebsiteCrawler.exe")
    assert error.value.status_code == 502 and "checksum" in error.value.detail
    assert not staging.exists()  # nothing half-downloaded is left to install


def test_download_update_refuses_entries_outside_the_folder(release_files, tmp_path):
    folder, base = release_files
    for bad_name in ("../evil.txt", "WebsiteCrawler/../../evil.txt", "/abs/evil.txt"):
        package = make_zip({"WebsiteCrawler/WebsiteCrawler.exe": b"new exe", bad_name: b"x"})
        (folder / server.UPDATE_ASSET).write_bytes(package)
        with pytest.raises(HTTPException) as error:
            server.download_update(f"{base}/{server.UPDATE_ASSET}", hashlib.sha256(package).hexdigest(),
                                   tmp_path / "_update", "WebsiteCrawler.exe")
        assert "outside" in error.value.detail
    assert not (tmp_path / "evil.txt").exists()
