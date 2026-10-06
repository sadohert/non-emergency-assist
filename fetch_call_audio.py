"""Download the audio and transcript of a conversation with the agent, for the video edit."""

import sys
from pathlib import Path

from common import load_state, make_client

OUT_DIR = Path("video/calls")
SPEAKER = {"user": "Caller", "agent": "Agent"}


def fetch(client, state: dict, out_dir: Path, conversation_id: str | None = None) -> Path:
    api = client.conversational_ai.conversations
    if conversation_id is None:
        if not state.get("agent_id"):
            raise SystemExit("No agent in state.json. Run agent.py first.")
        found = api.list(agent_id=state["agent_id"], page_size=20).conversations
        if not found:
            raise SystemExit("No conversations found for this agent yet.")
        conversation_id = max(found, key=lambda c: c.start_time_unix_secs).conversation_id

    detail = api.get(conversation_id)
    if not detail.has_audio:
        raise SystemExit(f"Conversation {conversation_id} has no audio. Record system audio instead.")

    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{conversation_id}.mp3"
    audio_path.write_bytes(b"".join(api.audio.get(conversation_id)))

    lines = [f"# Conversation {conversation_id}", ""]
    for turn in detail.transcript:
        if turn.message:
            lines.append(f"**{SPEAKER.get(turn.role, turn.role)}:** {turn.message}")
            lines.append("")
    (out_dir / f"{conversation_id}.md").write_text("\n".join(lines))
    return audio_path


def main() -> None:
    conversation_id = sys.argv[1] if len(sys.argv) > 1 else None
    print(fetch(make_client(), load_state(), OUT_DIR, conversation_id))


if __name__ == "__main__":
    main()
