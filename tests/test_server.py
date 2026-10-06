import httpx
import pytest
from fastapi.testclient import TestClient

import server

GOOD = {
    "topic": "Stolen bicycle",
    "summary": "Bike taken from front porch yesterday evening.",
    "first_name": "Alex",
    "callback_number": "416-555-0142",
}


@pytest.fixture
def posted(monkeypatch):
    """Capture posts to Mattermost and return 200."""
    calls = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(server.httpx, "post", fake_post)
    monkeypatch.setenv("TOOL_SHARED_SECRET", "s3cret")
    monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "http://mm.local/hooks/abc")
    return calls


client = TestClient(server.app)


def test_queues_callback_and_posts_to_mattermost(posted):
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": "s3cret"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert len(body["reference"]) == 6
    assert posted[0]["url"] == "http://mm.local/hooks/abc"
    text = posted[0]["json"]["text"]
    assert body["reference"] in text
    assert "Stolen bicycle" in text and "Alex" in text and "416-555-0142" in text


def test_rejects_wrong_secret(posted):
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": "nope"})
    assert r.status_code == 401
    assert posted == []


def test_rejects_missing_secret_header(posted):
    r = client.post("/tools/request_callback", json=GOOD)
    assert r.status_code == 401


def test_fails_closed_without_configured_secret(posted, monkeypatch):
    monkeypatch.delenv("TOOL_SHARED_SECRET")
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": ""})
    assert r.status_code == 401
    assert posted == []


def test_rejects_missing_number(posted):
    bad = {k: v for k, v in GOOD.items() if k != "callback_number"}
    r = client.post("/tools/request_callback", json=bad, headers={"X-Tool-Secret": "s3cret"})
    assert r.status_code == 422
    assert posted == []


def test_rejects_junk_number(posted):
    r = client.post(
        "/tools/request_callback",
        json={**GOOD, "callback_number": "call me whenever"},
        headers={"X-Tool-Secret": "s3cret"},
    )
    assert r.status_code == 422


def test_neutralizes_mentions_and_newlines(posted):
    r = client.post(
        "/tools/request_callback",
        json={**GOOD, "summary": "urgent @channel\n# BIG\n@all see http://x.test"},
        headers={"X-Tool-Secret": "s3cret"},
    )
    assert r.status_code == 200
    text = posted[0]["json"]["text"]
    assert "@channel" not in text and "@all" not in text
    summary_line = next(line for line in text.splitlines() if line.startswith("**Summary:**"))
    assert "BIG" in summary_line  # the injected newline was flattened onto the summary line


def test_502_when_mattermost_down(monkeypatch):
    monkeypatch.setenv("TOOL_SHARED_SECRET", "s3cret")
    monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "http://mm.local/hooks/abc")

    def boom(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(server.httpx, "post", boom)
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": "s3cret"})
    assert r.status_code == 502


def test_502_when_mattermost_rejects(monkeypatch):
    monkeypatch.setenv("TOOL_SHARED_SECRET", "s3cret")
    monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "http://mm.local/hooks/abc")
    monkeypatch.setattr(
        server.httpx,
        "post",
        lambda url, json, timeout: httpx.Response(403, request=httpx.Request("POST", url)),
    )
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": "s3cret"})
    assert r.status_code == 502


@pytest.mark.parametrize("number", ["-------", "       ", "(.....)", "416 555\n0142", "12345"])
def test_rejects_number_without_enough_digits(posted, number):
    r = client.post(
        "/tools/request_callback",
        json={**GOOD, "callback_number": number},
        headers={"X-Tool-Secret": "s3cret"},
    )
    assert r.status_code == 422
    assert posted == []


@pytest.mark.parametrize("field", ["topic", "summary", "first_name"])
def test_rejects_blank_fields(posted, field):
    r = client.post(
        "/tools/request_callback", json={**GOOD, field: "   "}, headers={"X-Tool-Secret": "s3cret"}
    )
    assert r.status_code == 422
    assert posted == []


def test_escapes_markdown_links_and_images(posted):
    r = client.post(
        "/tools/request_callback",
        json={**GOOD, "summary": "see [reset pw](http://evil.test) ![x](http://evil.test/p.png) `code` |cell|"},
        headers={"X-Tool-Secret": "s3cret"},
    )
    assert r.status_code == 200
    summary_line = next(
        line for line in posted[0]["json"]["text"].splitlines() if line.startswith("**Summary:**")
    )
    assert "](" not in summary_line
    assert "\\[reset pw\\]" in summary_line
    assert "\\`code\\`" in summary_line and "\\|cell\\|" in summary_line


def test_502_when_mattermost_redirects(monkeypatch):
    monkeypatch.setenv("TOOL_SHARED_SECRET", "s3cret")
    monkeypatch.setenv("MATTERMOST_WEBHOOK_URL", "http://mm.local/hooks/abc")
    monkeypatch.setattr(
        server.httpx,
        "post",
        lambda url, json, timeout: httpx.Response(302, request=httpx.Request("POST", url)),
    )
    r = client.post("/tools/request_callback", json=GOOD, headers={"X-Tool-Secret": "s3cret"})
    assert r.status_code == 502
