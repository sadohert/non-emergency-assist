import json

import httpx
import pytest

import clone_voice
import fetch_call_audio
import narrate

SCRIPT = """# Narration script

Intro text that is not in a section.

## 01-problem

First line.
Second line.

> an edit note

## 02-live-call

Only line.
"""


def test_parse_script_sections_and_strips_notes():
    assert narrate.parse_script(SCRIPT) == [
        ("01-problem", "First line. Second line."),
        ("02-live-call", "Only line."),
    ]


def test_parse_script_rejects_empty_section():
    with pytest.raises(SystemExit) as exc:
        narrate.parse_script("## 01-empty\n\n> only a note\n")
    assert "01-empty" in str(exc.value)


def tts_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"MP3:" + json.loads(request.content)["text"].encode())


def test_generate_writes_files_and_skips_unchanged(tmp_path, mock_client):
    client, seen = mock_client(tts_handler)
    state = {"clone_voice_id": "v1"}
    sections = narrate.parse_script(SCRIPT)

    paths = narrate.generate(client, sections, state, tmp_path)

    assert [p.name for p in paths] == ["01-problem.mp3", "02-live-call.mp3"]
    assert (tmp_path / "02-live-call.mp3").read_bytes() == b"MP3:Only line."
    assert seen[0].url.path == "/v1/text-to-speech/v1"
    assert json.loads(seen[0].content)["model_id"] == "eleven_multilingual_v2"

    narrate.generate(client, sections, state, tmp_path)
    assert len(seen) == 2  # nothing regenerated

    changed = [("01-problem", "New words."), sections[1]]
    narrate.generate(client, changed, state, tmp_path)
    assert len(seen) == 3
    assert (tmp_path / "01-problem.mp3").read_bytes() == b"MP3:New words."


def test_generate_regenerates_if_file_deleted(tmp_path, mock_client):
    client, seen = mock_client(tts_handler)
    state = {"clone_voice_id": "v1"}
    sections = [("01-problem", "Words.")]
    narrate.generate(client, sections, state, tmp_path)
    (tmp_path / "01-problem.mp3").unlink()

    narrate.generate(client, sections, state, tmp_path)

    assert len(seen) == 2


def test_generate_requires_clone(tmp_path, mock_client):
    client, _ = mock_client(tts_handler)
    with pytest.raises(SystemExit) as exc:
        narrate.generate(client, [("a", "b")], {}, tmp_path)
    assert "clone_voice.py" in str(exc.value)


def test_clone_records_voice_id(tmp_path, mock_client):
    sample = tmp_path / "voice-sample.m4a"
    sample.write_bytes(b"audio")
    client, seen = mock_client(
        lambda request: httpx.Response(200, json={"voice_id": "v9", "requires_verification": False})
    )
    state = {}

    assert clone_voice.clone(client, sample, state) == "v9"
    assert state["clone_voice_id"] == "v9"
    assert seen[0].url.path == "/v1/voices/add"


def test_clone_refuses_to_duplicate(tmp_path, mock_client):
    sample = tmp_path / "voice-sample.m4a"
    sample.write_bytes(b"audio")
    client, seen = mock_client(lambda request: httpx.Response(500))
    with pytest.raises(SystemExit) as exc:
        clone_voice.clone(client, sample, {"clone_voice_id": "v9"})
    assert "v9" in str(exc.value)
    assert seen == []


def test_clone_requires_sample(tmp_path, mock_client):
    client, _ = mock_client(lambda request: httpx.Response(500))
    with pytest.raises(SystemExit) as exc:
        clone_voice.clone(client, tmp_path / "missing.m4a", {})
    assert "missing.m4a" in str(exc.value)


def conversations_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/conversations"):
        return httpx.Response(
            200,
            json={
                "has_more": False,
                "conversations": [
                    {"agent_id": "agent_1", "conversation_id": "c_old", "start_time_unix_secs": 100,
                     "call_duration_secs": 30},
                    {"agent_id": "agent_1", "conversation_id": "c_new", "start_time_unix_secs": 200,
                     "call_duration_secs": 40},
                ],
            },
        )
    if path.endswith("/audio"):
        return httpx.Response(200, content=b"CALLAUDIO")
    return httpx.Response(
        200,
        json={
            "conversation_id": path.rsplit("/", 1)[-1],
            "agent_id": "agent_1",
            "status": "done",
            "has_audio": True,
            "transcript": [
                {"role": "user", "message": "Someone hit my car.", "time_in_call_secs": 2},
                {"role": "agent", "message": "Is anyone injured?", "time_in_call_secs": 4},
            ],
        },
    )


def test_fetch_defaults_to_most_recent(tmp_path, mock_client):
    client, _ = mock_client(conversations_handler)

    audio = fetch_call_audio.fetch(client, {"agent_id": "agent_1"}, tmp_path)

    assert audio == tmp_path / "c_new.mp3"
    assert audio.read_bytes() == b"CALLAUDIO"
    transcript = (tmp_path / "c_new.md").read_text()
    assert "**Caller:** Someone hit my car." in transcript
    assert "**Agent:** Is anyone injured?" in transcript


def test_fetch_specific_conversation(tmp_path, mock_client):
    client, seen = mock_client(conversations_handler)
    audio = fetch_call_audio.fetch(client, {"agent_id": "agent_1"}, tmp_path, "c_old")
    assert audio.name == "c_old.mp3"
    assert not any(r.url.path.endswith("/conversations") for r in seen)


def test_fetch_exits_when_no_conversations(tmp_path, mock_client):
    client, _ = mock_client(
        lambda request: httpx.Response(200, json={"has_more": False, "conversations": []})
    )
    with pytest.raises(SystemExit) as exc:
        fetch_call_audio.fetch(client, {"agent_id": "agent_1"}, tmp_path)
    assert "no conversations" in str(exc.value).lower()


def test_fetch_exits_when_no_audio(tmp_path, mock_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"conversation_id": "c1", "agent_id": "agent_1", "status": "done",
                  "has_audio": False, "transcript": []},
        )

    client, _ = mock_client(handler)
    with pytest.raises(SystemExit) as exc:
        fetch_call_audio.fetch(client, {"agent_id": "agent_1"}, tmp_path, "c1")
    assert "no audio" in str(exc.value).lower()


def test_clone_sends_labels_as_serialized_json(tmp_path, mock_client):
    """The live API rejects a clone request that has no labels; the SDK sends "null" when they are omitted."""
    sample = tmp_path / "voice-sample.m4a"
    sample.write_bytes(b"audio")
    client, seen = mock_client(
        lambda request: httpx.Response(200, json={"voice_id": "v9", "requires_verification": False})
    )

    clone_voice.clone(client, sample, {})

    body = seen[0].content
    assert b'name="labels"' in body
    assert b'{"language": "en"}' in body
