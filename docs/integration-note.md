# Integration note: a police non-emergency line on ElevenAgents

*Unofficial demonstration. Not affiliated with the Toronto Police Service.*

## What I built
A voice agent that answers routine non-emergency questions from 17 public Toronto Police Service pages, asks follow-up questions to route the caller, sends emergencies to 911, and takes callback requests into Mattermost. The knowledge base, agent, webhook tool and tests are all defined in Python through the ElevenLabs SDK. On the final configuration all 15 agent tests passed in each of three repeated runs (45 of 45), and I held 20 live voice conversations with it.

## Architecture
    caller → ElevenLabs (speech-to-text, agent LLM + knowledge base, text-to-speech)
           → webhook tool → Cloudflare tunnel → FastAPI → Mattermost

The tool is a webhook because it works under Zero Retention Mode, where MCP tools do not. Only the small FastAPI service is exposed; it checks a shared secret, validates and escapes the caller's details, and posts to Mattermost locally. If the call fails, the agent says the request was not logged and gives the published non-emergency number.

## What worked well
- **Everything through the API.** Uploading and indexing 17 documents, creating the agent and tool, and re-running to update them in place all worked as code.
- **Simulated-caller tests.** They hold a whole conversation and caught behaviour that single-reply tests could not.
- **Repeat runs.** Running each test three times exposed behaviours that failed one time in three and passed most single runs.

## What was rough
- **Errors only visible at run time.** The API rejected a voice model that the SDK's types list as valid for agents.
- **Undocumented test syntax.** The path for checking a webhook tool's parameters (`body.<name>`) had to be found by trial.
- **Secrets in test output.** Test results return the tool's secret header in plain text.
- **Passing tests hid defects.** The model's hidden reasoning was occasionally spoken aloud in runs that scored 42 of 42; turning its thinking off fixed it. The first unscripted question ("Where do I find bullets for my gun?") was wrongly sent to 911, because I had tested missed emergencies but not false alarms. I left that one unfixed.
- **Voice-only defects.** A phone number read as "four sixteen", and a callback that asked the same question twice, both passed every text test.

## Constraints a Canadian public-sector customer would raise
- **Where data lives.** Customer data is hosted in the US by default. Regional residency is an Enterprise feature covering the EU, India and Singapore, with no Canadian region, and processing may still occur outside the selected region.
- **What is exposed here.** The knowledge is already public. The exposure is caller audio, transcripts and three callback details.
- **How I would reduce it.** Zero Retention Mode, minimal personal details, and redacting transcripts after the call.
- **When that is not enough.** The custom-LLM option lets the customer host the model and retrieval, so ElevenLabs handles only speech. I did not build that here.
- **Secrets.** This demo sends the shared secret as a plain tool header. In production it belongs in workspace secrets.

## What a customer would want next
A false-alarm test set alongside the emergency tests; telephony through SIP into their phone system; handing a call to a live person; analytics on why people call; and Agent Workflows for larger call flows than prompt-only triage can hold.
