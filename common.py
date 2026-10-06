"""Shared helpers: the ElevenLabs client and the local record of created resource IDs."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import ElevenLabs

STATE_PATH = Path("state.json")
EMBED_MODEL = "e5_mistral_7b_instruct"


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def make_client() -> ElevenLabs:
    load_dotenv()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return ElevenLabs(api_key=key)
