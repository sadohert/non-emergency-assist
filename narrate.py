"""Generate one narration MP3 per section of video/script.md, in the user's cloned voice."""

import hashlib
from pathlib import Path

from common import load_state, make_client, save_state

SCRIPT_PATH = Path("video/script.md")
OUT_DIR = Path("video/narration")
MODEL = "eleven_multilingual_v2"


def parse_script(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections and line.strip() and not line.startswith(">"):
            sections[-1][1].append(line.strip())
    result = []
    for slug, lines in sections:
        if not lines:
            raise SystemExit(f"Section '{slug}' has no spoken text.")
        result.append((slug, " ".join(lines)))
    return result


def generate(client, sections: list[tuple[str, str]], state: dict, out_dir: Path) -> list[Path]:
    voice_id = state.get("clone_voice_id")
    if not voice_id:
        raise SystemExit("No cloned voice in state.json. Run clone_voice.py first.")
    out_dir.mkdir(parents=True, exist_ok=True)
    done = state.setdefault("narration", {})
    paths = []
    for slug, text in sections:
        path = out_dir / f"{slug}.mp3"
        digest = hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()
        if done.get(slug) == digest and path.exists():
            print(f"unchanged  {path}")
        else:
            audio = client.text_to_speech.convert(
                voice_id, text=text, model_id=MODEL, output_format="mp3_44100_128"
            )
            path.write_bytes(b"".join(audio))
            done[slug] = digest
            print(f"generated  {path}")
        paths.append(path)
    return paths


def main() -> None:
    state = load_state()
    generate(make_client(), parse_script(SCRIPT_PATH.read_text()), state, OUT_DIR)
    save_state(state)


if __name__ == "__main__":
    main()
