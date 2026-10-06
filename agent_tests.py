"""Sync the test cases in config/tests.yaml to ElevenLabs, run them, and write docs/test-results.md."""

import sys
import time
from datetime import date
from pathlib import Path

import yaml

from common import load_state, make_client, save_state

TESTS_PATH = Path("config/tests.yaml")
RESULTS_PATH = Path("docs/test-results.md")


def load_tests(path: Path = TESTS_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())


def _history(test: dict) -> list[dict]:
    history = [
        {"role": role, "message": message, "time_in_call_secs": i}
        for i, (role, message) in enumerate(test["history"])
    ]
    if not history or history[-1]["role"] != "user":
        raise SystemExit(f"Test '{test['name']}': history must end with a user message.")
    return history


def build_test_body(test: dict, state: dict) -> dict:
    kind = test["type"]
    if kind == "llm":
        return {
            "type": "llm",
            "name": test["name"],
            "chat_history": _history(test),
            "success_condition": test["success_condition"],
            "success_examples": [{"response": test["success_example"], "type": "success"}],
            "failure_examples": [{"response": test["failure_example"], "type": "failure"}],
        }
    if kind == "tool":
        expectation = {
            "referenced_tool": {"id": state["tool_id"], "type": "webhook"},
            "verify_absence": not test["expect_tool_call"],
        }
        if test.get("expect_params"):
            expectation["parameters"] = [
                # Webhook body parameters are addressed as "body.<name>" (confirmed against the live API).
                {"path": f"body.{name}", "eval": {"type": "regex", "pattern": pattern}}
                for name, pattern in test["expect_params"].items()
            ]
        return {
            "type": "tool",
            "name": test["name"],
            "chat_history": _history(test),
            "tool_call_parameters": expectation,
        }
    if kind == "simulation":
        return {
            "type": "simulation",
            "name": test["name"],
            "simulation_scenario": test["scenario"],
            "success_condition": test["success_condition"],
            "simulation_max_turns": test["max_turns"],
            "tool_mock_config": {"mocking_strategy": "all"},
        }
    raise SystemExit(f"Test '{test['name']}': unknown type '{kind}'.")


def sync_tests(client, tests: list[dict], state: dict) -> dict:
    api = client.conversational_ai.tests
    previous = state.get("test_ids", {})
    # Recorded as we go, so a failure partway through never loses a test that was created.
    ids: dict = {}
    state["test_ids"] = ids
    for test in tests:
        body = build_test_body(test, state)
        if test["name"] in previous:
            api.update(previous[test["name"]], request=body)
            ids[test["name"]] = previous[test["name"]]
        else:
            ids[test["name"]] = api.create(request=body).id
    return ids


def run_tests(client, state: dict, timeout: float = 600, sleep=time.sleep) -> list:
    if not state.get("agent_id"):
        raise SystemExit("No agent in state.json. Run agent.py first.")
    if not state.get("test_ids"):
        raise SystemExit("No tests in state.json. Sync tests first.")
    invocation = client.conversational_ai.agents.run_tests(
        state["agent_id"], tests=[{"test_id": tid} for tid in state["test_ids"].values()]
    )
    deadline = time.monotonic() + timeout
    while True:
        runs = client.conversational_ai.tests.invocations.get(invocation.id).test_runs
        if all(run.status != "pending" for run in runs):
            return runs
        if time.monotonic() >= deadline:
            raise SystemExit(f"Timed out waiting for test invocation {invocation.id}.")
        sleep(5)


def render_results(runs: list) -> str:
    passed = sum(1 for run in runs if run.status == "passed")
    lines = [
        "# Agent test results",
        "",
        f"Run on {date.today().isoformat()}: {passed} of {len(runs)} passed.",
        "",
        "| Test | Result | Evaluator's reasoning |",
        "|---|---|---|",
    ]
    for run in sorted(runs, key=lambda r: r.test_name or ""):
        rationale = ""
        if run.condition_result and run.condition_result.rationale:
            rationale = " ".join((run.condition_result.rationale.summary or "").split())
        lines.append(f"| {run.test_name} | {run.status} | {rationale.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    client = make_client()
    state = load_state()
    if not state.get("tool_id"):
        raise SystemExit("No tool in state.json. Run agent.py first.")
    try:
        sync_tests(client, load_tests(), state)
    finally:
        save_state(state)
    runs = run_tests(client, state)
    report = render_results(runs)
    RESULTS_PATH.write_text(report)
    print(report)
    if any(run.status != "passed" for run in runs):
        sys.exit(1)


if __name__ == "__main__":
    main()
