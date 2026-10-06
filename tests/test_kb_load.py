import hashlib
import json

import httpx
import pytest

import kb_load


def kb_handler(statuses=None):
    """Mock ElevenLabs: uploads get ids d1, d2, ...; rag-index returns the next status."""
    statuses = list(statuses or ["succeeded"])
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/knowledge-base/file"):
            counter["n"] += 1
            return httpx.Response(200, json={"id": f"d{counter['n']}", "name": "doc"})
        if path.endswith("/rag-index"):
            status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
            return httpx.Response(
                200,
                json={"id": "r", "model": "e5_mistral_7b_instruct", "status": status, "progress_percentage": 0},
            )
        return httpx.Response(404)

    return handler


def uploads(seen):
    return [r for r in seen if r.url.path.endswith("/knowledge-base/file")]


def test_uploads_new_files_and_records_them(tmp_path, mock_client):
    (tmp_path / "online-reporting.pdf").write_bytes(b"%PDF one")
    (tmp_path / "record-checks.txt").write_text("two")
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    client, seen = mock_client(kb_handler())
    state = {}

    docs = kb_load.sync_corpus(client, tmp_path, state)

    assert len(uploads(seen)) == 2
    assert set(docs) == {"online-reporting.pdf", "record-checks.txt"}
    assert docs["online-reporting.pdf"]["name"] == "online-reporting"
    assert docs["online-reporting.pdf"]["sha256"] == hashlib.sha256(b"%PDF one").hexdigest()
    assert state["kb_docs"] is docs


def test_skips_unchanged(tmp_path, mock_client):
    (tmp_path / "a.txt").write_text("same")
    client, seen = mock_client(kb_handler())
    state = {}
    kb_load.sync_corpus(client, tmp_path, state)
    first_id = state["kb_docs"]["a.txt"]["id"]

    kb_load.sync_corpus(client, tmp_path, state)

    assert len(uploads(seen)) == 1
    assert state["kb_docs"]["a.txt"]["id"] == first_id


def test_reuploads_changed(tmp_path, mock_client):
    (tmp_path / "a.txt").write_text("v1")
    client, seen = mock_client(kb_handler())
    state = {}
    kb_load.sync_corpus(client, tmp_path, state)
    (tmp_path / "a.txt").write_text("v2")

    kb_load.sync_corpus(client, tmp_path, state)

    assert len(uploads(seen)) == 2
    assert state["kb_docs"]["a.txt"]["id"] == "d2"


def test_drops_removed(tmp_path, mock_client):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    client, _ = mock_client(kb_handler())
    state = {}
    kb_load.sync_corpus(client, tmp_path, state)
    (tmp_path / "b.txt").unlink()

    kb_load.sync_corpus(client, tmp_path, state)

    assert set(state["kb_docs"]) == {"a.txt"}


def test_empty_corpus_exits(tmp_path, mock_client):
    client, _ = mock_client(kb_handler())
    with pytest.raises(SystemExit) as exc:
        kb_load.sync_corpus(client, tmp_path, {})
    assert "corpus" in str(exc.value).lower()


def test_wait_for_index_polls_until_succeeded(mock_client):
    client, seen = mock_client(kb_handler(["processing", "processing", "succeeded"]))
    assert kb_load.wait_for_index(client, "d1", sleep=lambda s: None) == "succeeded"
    assert len(seen) == 3
    assert json.loads(seen[0].content)["model"] == "e5_mistral_7b_instruct"


def test_wait_for_index_accepts_small_documents(mock_client):
    client, _ = mock_client(kb_handler(["document_too_small"]))
    assert kb_load.wait_for_index(client, "d1", sleep=lambda s: None) == "document_too_small"


def test_wait_for_index_exits_on_failure(mock_client):
    client, _ = mock_client(kb_handler(["rag_limit_exceeded"]))
    with pytest.raises(SystemExit) as exc:
        kb_load.wait_for_index(client, "d1", sleep=lambda s: None)
    assert "rag_limit_exceeded" in str(exc.value)


def test_wait_for_index_times_out(mock_client):
    client, _ = mock_client(kb_handler(["processing"]))
    with pytest.raises(SystemExit) as exc:
        kb_load.wait_for_index(client, "d1", timeout=0, sleep=lambda s: None)
    assert "timed out" in str(exc.value).lower()


def failing_second_upload():
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 2:
            return httpx.Response(400, json={"detail": "boom"})
        return httpx.Response(200, json={"id": f"d{counter['n']}", "name": "doc"})

    return handler


def test_failed_upload_keeps_earlier_uploads_in_state(tmp_path, mock_client):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    client, _ = mock_client(failing_second_upload())
    state = {}

    with pytest.raises(Exception):
        kb_load.sync_corpus(client, tmp_path, state)

    assert set(state["kb_docs"]) == {"a.txt"}


def test_main_saves_state_when_upload_fails(tmp_path, mock_client, monkeypatch):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    client, _ = mock_client(failing_second_upload())
    saved = []
    monkeypatch.setattr(kb_load, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(kb_load, "make_client", lambda: client)
    monkeypatch.setattr(kb_load, "load_state", lambda: {})
    monkeypatch.setattr(kb_load, "save_state", lambda state: saved.append(dict(state)))

    with pytest.raises(Exception):
        kb_load.main()

    assert set(saved[-1]["kb_docs"]) == {"a.txt"}
