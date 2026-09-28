from fastapi.testclient import TestClient

from server import VERSION, app

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_unknown_host_is_refused():
    # DNS rebinding: a page on attacker.test resolves its name to 127.0.0.1 and reads the API.
    assert client.get("/api/jobs", headers={"host": "attacker.test:8000"}).status_code == 400
    assert client.get("/", headers={"host": "attacker.test"}).status_code == 400
    assert client.get("/api/version", headers={"host": "127.0.0.1:notaport"}).status_code == 400
    assert client.get("/api/version").status_code == 200
    assert client.get("/api/version", headers={"host": "localhost:8000"}).status_code == 200


def test_cross_site_writes_are_refused():
    stop = "/api/jobs/no_such_job/stop"
    # Passes the guard, then 404 because the job does not exist.
    assert client.post(stop, json={}).status_code == 404
    assert client.post(stop, json={}, headers={"origin": "http://127.0.0.1:8000", "sec-fetch-site": "same-origin"}).status_code == 404
    assert client.post(stop, json={}, headers={"origin": "http://localhost:8000"}).status_code == 404

    assert client.post(stop, json={}, headers={"origin": "https://evil.test"}).status_code == 403
    assert client.post(stop, json={}, headers={"origin": "http://127.0.0.1:9000"}).status_code == 403
    assert client.post(stop, json={}, headers={"origin": "null"}).status_code == 403
    assert client.post(stop, json={}, headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post(stop, json={}, headers={"sec-fetch-site": "same-site"}).status_code == 403
    # A cross-site <form> or no-cors fetch can only send these content types.
    assert client.post(stop).status_code == 403
    assert client.post(stop, content="{}", headers={"content-type": "text/plain"}).status_code == 403
    assert client.post(stop, data={"a": "1"}).status_code == 403
    assert client.request("DELETE", "/api/jobs/no_such_job").status_code == 403
    assert client.post("/api/update/install").status_code == 403


def test_reads_need_only_the_host():
    # Exports and the log stream are opened by navigation / EventSource, which cannot set headers.
    assert client.get("/api/jobs", headers={"origin": "https://evil.test"}).status_code == 200


def test_index_is_not_cached_and_versions_its_assets():
    for path in ("/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert f'src="/app.js?v={VERSION}"' in response.text
        assert f'href="/app.css?v={VERSION}"' in response.text
    assert client.get(f"/app.js?v={VERSION}").status_code == 200
