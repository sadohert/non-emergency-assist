# Non-Emergency Assist

**Independent demonstration. Not affiliated with, endorsed by, or operated by the Toronto Police Service or ElevenLabs.**

A voice agent built on [ElevenLabs ElevenAgents](https://elevenlabs.io) that answers routine police non-emergency questions from public Toronto Police Service web pages. It asks follow-up questions to route the caller, sends emergencies to 911, and takes callback requests into a Mattermost channel.

Everything on the ElevenLabs side is defined in Python: the knowledge base, the agent, its webhook tool and its tests.

**Watch the three-minute demo:** https://youtu.be/lKWT9Cqh-WA

I built this to get hands-on experience with the ElevenLabs platform. I chose the scenario, made the design decisions, tested it by voice and wrote up the findings. Claude Code was my coding assistant and wrote most of the code under my direction.

## What it does

- **Answers from a fixed set of public pages.** The agent's knowledge is 17 pages saved from tps.ca. It is told to answer only from them and to name the page it used.
- **Triage by conversation.** For a collision, a theft or an unclear situation, it asks one short question at a time before giving guidance.
- **Emergencies first.** Anything that sounds like danger gets "hang up and call 911", and the agent stops there.
- **Callbacks.** When the caller wants a person, the agent collects a summary, a first name and a number, and a webhook posts the request to a Mattermost channel.

## Results

- **Agent tests:** 15 tests, including two simulated-caller conversations. On the final configuration all 15 passed in each of three repeated runs (45 of 45). See [docs/test-results.md](docs/test-results.md).
- **Unit tests:** 88, all offline, using a mocked network layer.
- **Live calls:** 20 voice conversations with the agent.

The most useful findings were the failures:

- The agent passed 42 of 42 test runs while occasionally speaking its own reasoning aloud. The tests did not check for it; reading transcripts did.
- The first unscripted question asked by voice ("Where do I find bullets for my gun?") was wrongly sent to 911. The tests covered missed emergencies but not false alarms. This is left unfixed and documented.
- A phone number read as "four sixteen" passed every text-based test.

The full account is in [docs/integration-note.md](docs/integration-note.md) (one page) and [docs/live-notes.md](docs/live-notes.md) (detailed observations).

## How it fits together

    caller → ElevenLabs (speech-to-text, agent LLM + knowledge base, text-to-speech)
           → webhook tool → tunnel → server.py (FastAPI) → Mattermost

| File | What it does |
|---|---|
| `config/agent.yaml` | The agent: prompt, models, voice, and the webhook tool's definition |
| `config/tests.yaml` | The 15 agent tests, as data |
| `kb_load.py` | Uploads `corpus/` to the knowledge base and waits for indexing |
| `agent.py` | Creates or updates the webhook tool and the agent |
| `server.py` | Receives `request_callback`, validates it, and posts to Mattermost |
| `agent_tests.py` | Syncs the tests to ElevenLabs, runs them, and writes `docs/test-results.md` |
| `clone_voice.py`, `narrate.py`, `fetch_call_audio.py` | Voice clone, narration and call-audio helpers used for the demo video |
| `video/` | The narration script, captions, and the scripts that render the video's animated sections |

Created resource IDs are kept in a local `state.json`, so every script can be re-run safely.

## Run it

You need an ElevenLabs account with API access, Python 3.11+, [uv](https://docs.astral.sh/uv/), a Mattermost incoming webhook (or any URL that accepts a JSON POST), and a tunnel such as `cloudflared`.

    cp .env.example .env          # fill in the four values
    uv sync
    uv run pytest                 # offline unit tests
    uv run uvicorn server:app --port 8000
    cloudflared tunnel --url http://localhost:8000   # put the URL in .env as TOOL_BASE_URL
    uv run python kb_load.py
    uv run python agent.py
    uv run python agent_tests.py

Re-run `agent.py` whenever the tunnel URL, the prompt or the corpus changes. Running the agent tests uses ElevenLabs credits.

## Corpus

The source pages are not included in this repository. They were saved from tps.ca as PDFs on 2026-10-06 into `corpus/`:

| File | Source |
|---|---|
| `non-emergency-contact.pdf` | https://www.tps.ca/contact/416-808-2222-police-non-emergency/ |
| `contact.pdf` | https://www.tps.ca/contact/ |
| `online-reporting.pdf` | https://www.tps.ca/services/online-reporting/ |
| `collision-reporting.pdf` | https://www.tps.ca/services/collision-reporting/ |
| `damage-to-vehicle-under-5000.pdf` | https://www.tps.ca/services/online-reporting/damage-vehicle-under-5000/ |
| `police-record-checks.pdf` | https://www.tps.ca/services/police-record-checks/ |
| `lost-property-or-identification.pdf` | https://www.tps.ca/services/online-reporting/lost-property-or-identification-resources/ |
| `property-identification-program.pdf` | https://www.tps.ca/services/property-identification-program/ |
| `fraud.pdf` | https://www.tps.ca/fraud/ |
| `bicycle-safety-and-theft-prevention.pdf` | https://www.tps.ca/crime-prevention/bicycle-safety-and-theft-prevention/ |
| `freedom-of-information-request.pdf` | https://www.tps.ca/services/freedom-information-request/ |
| `records-release.pdf` | https://www.tps.ca/services/records-release/ |
| `services-overview.pdf` | https://www.tps.ca/services/ |
| `911-emergency.pdf`, `make-the-right-call.pdf`, `community-crisis-service.pdf`, `toronto-at-your-service-311.pdf` | Pages linked from https://www.tps.ca/contact/ |

## Known limitations

- **False alarms.** The agent leans toward sending callers to 911. There is no test set of harmless questions that contain alarming words.
- **One model.** The prompt was tuned on Gemini 2.5 Flash. Two other models failed safety tests on the same prompt; switching models means re-tuning.
- **Demo-grade plumbing.** The webhook's shared secret is sent as a plain tool header, the tunnel address is temporary, and old knowledge-base documents are not cleaned up.
- **Data residency.** ElevenLabs hosts customer data in the US by default, with no Canadian region. The integration note discusses how to design around that.

## Licence

MIT. See [LICENSE](LICENSE).
