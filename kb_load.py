"""Sync the files in corpus/ to the ElevenLabs knowledge base and wait for RAG indexing."""

import hashlib
import mimetypes
import time
from pathlib import Path

from common import EMBED_MODEL, load_state, make_client, save_state

CORPUS_DIR = Path("corpus")
SUPPORTED = {".pdf", ".txt", ".md", ".html", ".docx", ".epub"}
DONE = {"succeeded", "document_too_small"}
FAILED = {"failed", "rag_limit_exceeded", "cannot_index_folder"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_corpus(client, corpus_dir: Path, state: dict) -> dict:
    files = sorted(p for p in corpus_dir.glob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(f"No corpus files found in {corpus_dir}/. Save the source pages there first.")

    previous = state.get("kb_docs", {})
    names = {path.name for path in files}
    # Recorded as we go, so a failure partway through never loses an upload that succeeded.
    docs: dict = {name: doc for name, doc in previous.items() if name in names}
    state["kb_docs"] = docs
    for path in files:
        digest = _sha256(path)
        known = previous.get(path.name)
        if known and known["sha256"] == digest:
            print(f"unchanged  {path.name}")
            continue
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            created = client.conversational_ai.knowledge_base.documents.create_from_file(
                file=(path.name, fh, mime), name=path.stem
            )
        docs[path.name] = {"id": created.id, "name": path.stem, "sha256": digest}
        print(f"{'replaced ' if known else 'uploaded '} {path.name} -> {created.id}")

    for name in sorted(set(previous) - set(docs)):
        print(f"removed    {name} (detached; the old document stays in the workspace)")

    return docs


def wait_for_index(client, doc_id: str, timeout: float = 300, sleep=time.sleep) -> str:
    deadline = time.monotonic() + timeout
    while True:
        status = client.conversational_ai.knowledge_base.document.compute_rag_index(
            doc_id, model=EMBED_MODEL
        ).status
        if status in DONE:
            return status
        if status in FAILED:
            raise SystemExit(f"RAG indexing failed for {doc_id}: {status}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"Timed out waiting for RAG index on {doc_id} (last status: {status})")
        sleep(3)


def main() -> None:
    client = make_client()
    state = load_state()
    try:
        docs = sync_corpus(client, CORPUS_DIR, state)
    finally:
        save_state(state)
    for name, doc in docs.items():
        print(f"index      {name}: {wait_for_index(client, doc['id'])}")
    print(f"{len(docs)} documents ready. Run agent.py to attach them.")


if __name__ == "__main__":
    main()
