"""Create an instant voice clone of the user for video narration. Never used as the agent's voice."""

import sys
from pathlib import Path

from common import load_state, make_client, save_state

CLONE_NAME = "Narration (my own voice)"


def clone(client, sample: Path, state: dict, name: str = CLONE_NAME) -> str:
    if state.get("clone_voice_id"):
        raise SystemExit(
            f"A clone already exists ({state['clone_voice_id']}). "
            "Remove clone_voice_id from state.json to make a new one."
        )
    if not sample.exists():
        raise SystemExit(f"Voice sample not found: {sample}")
    with sample.open("rb") as fh:
        created = client.voices.ivc.create(
            name=name,
            files=[fh],
            remove_background_noise=True,
            # Always pass labels: when they are omitted the SDK sends "null", which the API rejects.
            labels={"language": "en"},
        )
    state["clone_voice_id"] = created.voice_id
    return created.voice_id


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python clone_voice.py video/voice-sample.m4a")
    state = load_state()
    voice_id = clone(make_client(), Path(sys.argv[1]), state)
    save_state(state)
    print(f"clone {voice_id}")


if __name__ == "__main__":
    main()
