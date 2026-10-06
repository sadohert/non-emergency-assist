import json

import httpx
import pytest

import agent

CFG = agent.load_config()
DOCS = {
    "b.pdf": {"id": "d2", "name": "b", "sha256": "x"},
    "a.pdf": {"id": "d1", "name": "a", "sha256": "y"},
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/convai/tools") or "/convai/tools/" in path:
        return httpx.Response(200, json={"id": "tool_1"})
    if path.endswith("/agents/create") or "/convai/agents/" in path:
        return httpx.Response(200, json={"agent_id": "agent_1"})
    return httpx.Response(404)


def test_config_puts_emergency_rule_first_and_has_disclaimer():
    prompt = CFG["prompt"]
    assert prompt.index("Rule 1: emergencies") < prompt.index("Rule 2")
    assert "unofficial" in CFG["first_message"].lower()
    assert "nine one one" in CFG["first_message"].lower()


def test_build_tool_request():
    req = agent.build_tool_request(CFG, "https://x.trycloudflare.com", "s3cret")
    tool = req["tool_config"]
    assert tool["type"] == "webhook"
    assert tool["name"] == "request_callback"
    api = tool["api_schema"]
    assert api["url"] == "https://x.trycloudflare.com/tools/request_callback"
    assert api["method"] == "POST"
    assert api["request_headers"] == {"X-Tool-Secret": "s3cret"}
    body = api["request_body_schema"]
    assert body["type"] == "object"
    assert sorted(body["required"]) == ["callback_number", "first_name", "summary", "topic"]
    assert body["properties"]["topic"]["type"] == "string"


def test_build_tool_request_strips_trailing_slash():
    req = agent.build_tool_request(CFG, "https://x.trycloudflare.com/", "s")
    assert req["tool_config"]["api_schema"]["url"] == "https://x.trycloudflare.com/tools/request_callback"


@pytest.mark.parametrize("bad", ["", "http://x.test", "x.trycloudflare.com"])
def test_build_tool_request_requires_https(bad):
    with pytest.raises(SystemExit) as exc:
        agent.build_tool_request(CFG, bad, "s")
    assert "TOOL_BASE_URL" in str(exc.value)


def test_build_tool_request_requires_secret():
    with pytest.raises(SystemExit) as exc:
        agent.build_tool_request(CFG, "https://x.test", "")
    assert "TOOL_SHARED_SECRET" in str(exc.value)


def test_build_conversation_config():
    conv = agent.build_conversation_config(CFG, {"kb_docs": DOCS, "tool_id": "tool_1"})
    a = conv["agent"]
    assert a["first_message"] == CFG["first_message"]
    p = a["prompt"]
    assert p["llm"] == CFG["llm"]
    assert p["tool_ids"] == ["tool_1"]
    assert p["rag"] == {"enabled": True, "embedding_model": "e5_mistral_7b_instruct"}
    assert p["knowledge_base"] == [
        {"type": "file", "name": "a", "id": "d1", "usage_mode": "auto"},
        {"type": "file", "name": "b", "id": "d2", "usage_mode": "auto"},
    ]
    assert conv["tts"] == {"voice_id": CFG["voice_id"], "model_id": "eleven_flash_v2"}


def test_build_conversation_config_requires_docs():
    with pytest.raises(SystemExit) as exc:
        agent.build_conversation_config(CFG, {"tool_id": "tool_1"})
    assert "kb_load.py" in str(exc.value)


def test_sync_creates_tool_then_agent(mock_client):
    client, seen = mock_client(handler)
    state = {"kb_docs": DOCS}

    agent.sync(client, CFG, state, "https://x.test", "s")

    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/v1/convai/tools"),
        ("POST", "/v1/convai/agents/create"),
    ]
    assert state["tool_id"] == "tool_1" and state["agent_id"] == "agent_1"
    sent = json.loads(seen[1].content)
    assert sent["name"] == CFG["name"]
    assert sent["conversation_config"]["agent"]["prompt"]["tool_ids"] == ["tool_1"]


def test_sync_updates_when_ids_exist(mock_client):
    client, seen = mock_client(handler)
    state = {"kb_docs": DOCS, "tool_id": "tool_1", "agent_id": "agent_1"}

    agent.sync(client, CFG, state, "https://new.test", "s")

    assert [(r.method, r.url.path) for r in seen] == [
        ("PATCH", "/v1/convai/tools/tool_1"),
        ("PATCH", "/v1/convai/agents/agent_1"),
    ]
    assert "https://new.test/tools/request_callback" in seen[0].content.decode()


def test_sync_without_docs_makes_no_calls(mock_client):
    client, seen = mock_client(handler)
    with pytest.raises(SystemExit):
        agent.sync(client, CFG, {}, "https://x.test", "s")
    assert seen == []


def test_prompt_gives_fallback_number_without_retrieval():
    assert CFG["fallback_number"] in CFG["prompt"]


def test_prompt_reasks_on_invalid_details_and_discloses_demo_at_readback():
    callbacks = CFG["prompt"].split("# Callbacks")[1].split("# Style")[0].lower()
    assert "invalid" in callbacks and "ask for that detail again" in " ".join(callbacks.split())
    assert "demonstration" in callbacks and "no one from toronto police will" in " ".join(callbacks.split())


def test_main_saves_tool_id_when_agent_create_fails(mock_client, monkeypatch):
    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/convai/tools"):
            return httpx.Response(200, json={"id": "tool_1"})
        return httpx.Response(422, json={"detail": "bad voice"})

    client, _ = mock_client(flaky)
    saved = []
    monkeypatch.setattr(agent, "make_client", lambda: client)
    monkeypatch.setattr(agent, "load_state", lambda: {"kb_docs": DOCS})
    monkeypatch.setattr(agent, "save_state", lambda state: saved.append(dict(state)))
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)
    monkeypatch.setenv("TOOL_BASE_URL", "https://x.test")
    monkeypatch.setenv("TOOL_SHARED_SECRET", "s")

    with pytest.raises(Exception):
        agent.main()

    assert saved[-1]["tool_id"] == "tool_1"


def test_prompt_does_not_offer_callbacks_for_off_topic_questions():
    rule4 = " ".join(CFG["prompt"].split("# Rule 4")[1].split("# Callbacks")[0].lower().split())
    assert "nothing to do with policing" in rule4 and "do not offer a callback for an off-topic" in rule4
    assert "in the same reply offer a callback" in rule4


def test_prompt_asks_about_danger_when_situation_is_only_unclear():
    rule1 = " ".join(CFG["prompt"].split("# Rule 1")[1].split("# Rule 2")[0].lower().split())
    assert "ask whether anyone is in danger right now" in rule1
    assert "say goodbye" in rule1


def test_prompt_puts_caller_uncertainty_above_the_unclear_situation_question():
    rule1 = " ".join(CFG["prompt"].split("# Rule 1")[1].split("# Rule 2")[0].lower().split())
    assert "never ask the danger question" in rule1
    assert rule1.index("ask whether anyone is in danger right now") < rule1.index("never ask the danger question")


def test_prompt_requires_naming_the_source_in_every_grounded_answer():
    rule2 = " ".join(CFG["prompt"].split("# Rule 2")[1].split("# Rule 3")[0].lower().split())
    assert "every answer" in rule2 and "start it by naming" in rule2


def test_prompt_answers_after_triage_instead_of_offering_a_callback():
    rule3 = " ".join(CFG["prompt"].split("# Rule 3")[1].split("# Rule 4")[0].lower().split())
    assert "once triage is complete, give the guidance" in rule3
    assert "never log a callback in place of an answer" in rule3


def test_conversation_config_turns_model_thinking_off():
    conv = agent.build_conversation_config(CFG, {"kb_docs": DOCS, "tool_id": "tool_1"})
    assert CFG["thinking_budget"] == 0
    assert conv["agent"]["prompt"]["thinking_budget"] == 0


def test_prompt_says_phone_numbers_one_digit_at_a_time():
    style = " ".join(CFG["prompt"].split("# Style")[1].lower().split())
    assert "one digit at a time" in style
    assert "four one six, eight zero eight, two two two two" in style


def test_prompt_callback_asks_once_and_discloses_before_confirmation():
    callbacks = " ".join(CFG["prompt"].split("# Callbacks")[1].split("# Style")[0].lower().split())
    assert "never ask for a topic separately" in callbacks
    assert "together in one question" in callbacks
    assert callbacks.index("this is a demonstration") < callbacks.index("only call request_callback after a clear yes")


def test_tool_topic_is_written_by_the_agent():
    assert "do not ask the caller" in CFG["tool"]["properties"]["topic"]["description"].lower()
