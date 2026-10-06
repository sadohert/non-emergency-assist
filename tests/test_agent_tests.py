import json

import httpx
import pytest

import agent_tests

STATE = {"agent_id": "agent_1", "tool_id": "tool_1"}


def test_shipped_tests_are_well_formed():
    tests = agent_tests.load_tests()
    names = [t["name"] for t in tests]
    assert len(names) == len(set(names)) == 15
    for t in tests:
        body = agent_tests.build_test_body(t, STATE)
        assert body["type"] in {"llm", "tool", "simulation"}
        if body["type"] != "simulation":
            assert body["chat_history"][-1]["role"] == "user"


def test_build_llm_body():
    body = agent_tests.build_test_body(
        {
            "name": "n",
            "type": "llm",
            "history": [["user", "hi"], ["agent", "hello"], ["user", "help"]],
            "success_condition": "c",
            "success_example": "good",
            "failure_example": "bad",
        },
        STATE,
    )
    assert body == {
        "type": "llm",
        "name": "n",
        "chat_history": [
            {"role": "user", "message": "hi", "time_in_call_secs": 0},
            {"role": "agent", "message": "hello", "time_in_call_secs": 1},
            {"role": "user", "message": "help", "time_in_call_secs": 2},
        ],
        "success_condition": "c",
        "success_examples": [{"response": "good", "type": "success"}],
        "failure_examples": [{"response": "bad", "type": "failure"}],
    }


def test_build_tool_body_expecting_call():
    body = agent_tests.build_test_body(
        {"name": "n", "type": "tool", "expect_tool_call": True, "history": [["user", "x"]]}, STATE
    )
    assert body["type"] == "tool"
    assert body["tool_call_parameters"] == {
        "referenced_tool": {"id": "tool_1", "type": "webhook"},
        "verify_absence": False,
    }


def test_build_tool_body_expecting_no_call():
    body = agent_tests.build_test_body(
        {"name": "n", "type": "tool", "expect_tool_call": False, "history": [["user", "x"]]}, STATE
    )
    assert body["tool_call_parameters"]["verify_absence"] is True


def test_build_simulation_body_mocks_tools():
    body = agent_tests.build_test_body(
        {"name": "n", "type": "simulation", "scenario": "s", "success_condition": "c", "max_turns": 6},
        STATE,
    )
    assert body == {
        "type": "simulation",
        "name": "n",
        "simulation_scenario": "s",
        "success_condition": "c",
        "simulation_max_turns": 6,
        "tool_mock_config": {"mocking_strategy": "all"},
    }


def test_build_rejects_history_ending_with_agent():
    with pytest.raises(SystemExit) as exc:
        agent_tests.build_test_body(
            {"name": "bad", "type": "llm", "history": [["agent", "hi"]], "success_condition": "c",
             "success_example": "a", "failure_example": "b"},
            STATE,
        )
    assert "bad" in str(exc.value)


def test_build_rejects_unknown_type():
    with pytest.raises(SystemExit):
        agent_tests.build_test_body({"name": "n", "type": "voice"}, STATE)


def test_sync_creates_new_and_updates_existing(mock_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "t_new"})

    client, seen = mock_client(handler)
    tests = [
        {"name": "old", "type": "simulation", "scenario": "s", "success_condition": "c", "max_turns": 4},
        {"name": "new", "type": "simulation", "scenario": "s", "success_condition": "c", "max_turns": 4},
    ]
    state = {**STATE, "test_ids": {"old": "t_old", "gone": "t_gone"}}

    ids = agent_tests.sync_tests(client, tests, state)

    assert [(r.method, r.url.path) for r in seen] == [
        ("PUT", "/v1/convai/agent-testing/t_old"),
        ("POST", "/v1/convai/agent-testing/create"),
    ]
    assert ids == {"old": "t_old", "new": "t_new"}
    assert state["test_ids"] is ids


def invocation(statuses):
    return {
        "id": "inv1",
        "test_runs": [
            {
                "test_run_id": f"r{i}",
                "test_invocation_id": "inv1",
                "agent_id": "agent_1",
                "status": status,
                "test_id": f"t{i}",
                "test_name": f"test-{i}",
                "condition_result": {"result": "success", "rationale": {"summary": f"why {i}"}},
            }
            for i, status in enumerate(statuses)
        ],
    }


def test_run_tests_polls_until_no_pending(mock_client):
    responses = [invocation(["pending", "pending"]), invocation(["passed", "pending"]),
                 invocation(["passed", "failed"])]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    client, seen = mock_client(handler)
    state = {**STATE, "test_ids": {"a": "t0", "b": "t1"}}

    runs = agent_tests.run_tests(client, state, sleep=lambda s: None)

    assert [r.status for r in runs] == ["passed", "failed"]
    assert seen[0].method == "POST" and seen[0].url.path == "/v1/convai/agents/agent_1/run-tests"
    assert json.loads(seen[0].content)["tests"] == [{"test_id": "t0"}, {"test_id": "t1"}]
    assert [r.url.path for r in seen[1:]] == ["/v1/convai/test-invocations/inv1"] * 2


def test_run_tests_times_out(mock_client):
    client, _ = mock_client(lambda request: httpx.Response(200, json=invocation(["pending"])))
    with pytest.raises(SystemExit) as exc:
        agent_tests.run_tests(client, {**STATE, "test_ids": {"a": "t0"}}, timeout=0, sleep=lambda s: None)
    assert "timed out" in str(exc.value).lower()


def test_run_tests_requires_agent_and_tests(mock_client):
    client, seen = mock_client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(SystemExit):
        agent_tests.run_tests(client, {"test_ids": {"a": "t0"}})
    with pytest.raises(SystemExit):
        agent_tests.run_tests(client, {"agent_id": "agent_1", "test_ids": {}})
    assert seen == []


def test_render_results(mock_client):
    client, _ = mock_client(lambda request: httpx.Response(200, json=invocation(["passed", "failed"])))
    runs = client.conversational_ai.tests.invocations.get("inv1").test_runs

    md = agent_tests.render_results(runs)

    assert "1 of 2 passed" in md
    assert "| test-0 | passed | why 0 |" in md
    assert "| test-1 | failed | why 1 |" in md


def test_build_tool_body_checks_parameters():
    body = agent_tests.build_test_body(
        {
            "name": "n",
            "type": "tool",
            "expect_tool_call": True,
            "expect_params": {"callback_number": r"416\D*555\D*0142", "first_name": "(?i)^alex$"},
            "history": [["user", "x"]],
        },
        STATE,
    )
    assert body["tool_call_parameters"]["parameters"] == [
        {"path": "body.callback_number", "eval": {"type": "regex", "pattern": r"416\D*555\D*0142"}},
        {"path": "body.first_name", "eval": {"type": "regex", "pattern": "(?i)^alex$"}},
    ]


def test_shipped_callback_test_checks_number_and_name():
    test = next(t for t in agent_tests.load_tests() if t["name"] == "callback-calls-tool")
    assert set(test["expect_params"]) >= {"callback_number", "first_name"}


def test_shipped_missing_number_test_reaches_the_number_question():
    test = next(t for t in agent_tests.load_tests() if t["name"] == "callback-missing-number")
    assert len(test["history"]) >= 3
    assert "number" in test["history"][-2][1].lower()


def test_sync_keeps_created_ids_when_a_later_create_fails(mock_client):
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 2:
            return httpx.Response(400, json={"detail": "boom"})
        return httpx.Response(200, json={"id": "t_first"})

    client, _ = mock_client(handler)
    tests = [
        {"name": n, "type": "simulation", "scenario": "s", "success_condition": "c", "max_turns": 4}
        for n in ("first", "second")
    ]
    state = {**STATE}

    with pytest.raises(Exception):
        agent_tests.sync_tests(client, tests, state)

    assert state["test_ids"] == {"first": "t_first"}


def test_main_saves_state_when_sync_fails(mock_client, monkeypatch):
    client, _ = mock_client(lambda request: httpx.Response(400, json={"detail": "boom"}))
    saved = []
    monkeypatch.setattr(agent_tests, "make_client", lambda: client)
    monkeypatch.setattr(agent_tests, "load_state", lambda: {**STATE, "test_ids": {"keep": "t_keep"}})
    monkeypatch.setattr(agent_tests, "save_state", lambda state: saved.append(dict(state)))

    with pytest.raises(Exception):
        agent_tests.main()

    assert saved, "state must be saved even when syncing fails"
