import pytest

import common


def test_load_state_missing_file_returns_empty(tmp_path):
    assert common.load_state(tmp_path / "state.json") == {}


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "state.json"
    common.save_state({"agent_id": "a1", "kb_docs": {"x.pdf": {"id": "d1"}}}, path)
    assert common.load_state(path) == {"agent_id": "a1", "kb_docs": {"x.pdf": {"id": "d1"}}}


def test_make_client_exits_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(common, "load_dotenv", lambda: None)
    with pytest.raises(SystemExit) as exc:
        common.make_client()
    assert "ELEVENLABS_API_KEY" in str(exc.value)


def test_make_client_with_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "abc")
    assert common.make_client() is not None
