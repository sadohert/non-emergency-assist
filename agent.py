"""Create or update the Non-Emergency Assist agent and its webhook tool from config/agent.yaml."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from common import EMBED_MODEL, load_state, make_client, save_state

CONFIG_PATH = Path("config/agent.yaml")


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def build_tool_request(cfg: dict, base_url: str, secret: str) -> dict:
    if not base_url.startswith("https://"):
        raise SystemExit("TOOL_BASE_URL must be the https:// URL of the tunnel in front of server.py.")
    if not secret:
        raise SystemExit("TOOL_SHARED_SECRET is not set.")
    tool = cfg["tool"]
    return {
        "tool_config": {
            "type": "webhook",
            "name": tool["name"],
            "description": tool["description"],
            "response_timeout_secs": 10,
            "api_schema": {
                "url": f"{base_url.rstrip('/')}/tools/{tool['name']}",
                "method": "POST",
                "request_headers": {"X-Tool-Secret": secret},
                "request_body_schema": {
                    "type": "object",
                    "required": sorted(tool["properties"]),
                    "properties": tool["properties"],
                },
            },
        }
    }


def build_conversation_config(cfg: dict, state: dict) -> dict:
    docs = state.get("kb_docs") or {}
    if not docs:
        raise SystemExit("No knowledge-base documents in state.json. Run kb_load.py first.")
    return {
        "agent": {
            "first_message": cfg["first_message"],
            "language": cfg["language"],
            "prompt": {
                "prompt": cfg["prompt"],
                "llm": cfg["llm"],
                "temperature": cfg["temperature"],
                "thinking_budget": cfg["thinking_budget"],
                "tool_ids": [state["tool_id"]],
                "knowledge_base": [
                    {"type": "file", "name": doc["name"], "id": doc["id"], "usage_mode": "auto"}
                    for _, doc in sorted(docs.items())
                ],
                "rag": {"enabled": True, "embedding_model": EMBED_MODEL},
            },
        },
        "tts": {"voice_id": cfg["voice_id"], "model_id": cfg["tts_model"]},
    }


def sync(client, cfg: dict, state: dict, base_url: str, secret: str) -> dict:
    if not state.get("kb_docs"):
        raise SystemExit("No knowledge-base documents in state.json. Run kb_load.py first.")
    tool_request = build_tool_request(cfg, base_url, secret)

    tools = client.conversational_ai.tools
    if state.get("tool_id"):
        tools.update(state["tool_id"], request=tool_request)
    else:
        state["tool_id"] = tools.create(request=tool_request).id

    conversation_config = build_conversation_config(cfg, state)
    agents = client.conversational_ai.agents
    if state.get("agent_id"):
        agents.update(state["agent_id"], name=cfg["name"], conversation_config=conversation_config)
    else:
        state["agent_id"] = agents.create(
            name=cfg["name"], conversation_config=conversation_config
        ).agent_id
    return state


def main() -> None:
    load_dotenv()
    client = make_client()
    state = load_state()
    try:
        sync(
            client,
            load_config(),
            state,
            os.environ.get("TOOL_BASE_URL", ""),
            os.environ.get("TOOL_SHARED_SECRET", ""),
        )
    finally:
        save_state(state)
    print(f"tool  {state['tool_id']}")
    print(f"agent {state['agent_id']}")
    print(f"talk  https://elevenlabs.io/app/talk-to?agent_id={state['agent_id']}")


if __name__ == "__main__":
    main()
