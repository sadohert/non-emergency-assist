# Live notes

Observations from running against the real ElevenLabs service on 2026-10-06. Source material for the integration note.

## Bring-up

- **Knowledge base:** 17 PDFs uploaded and indexed through the API on the first attempt. Every document reached `succeeded`. The whole run took a few minutes.
- **Stock voice:** the voice ID taken from older documentation (`21m00Tcm4TlvDq8ikWAM`) was not on the account. Listed the account's voices through the API and chose "Sarah".
- **Agent create, first attempt failed:** the API rejected `eleven_flash_v2_5` with "English Agents must use turbo or flash v2". The SDK's type hints list both as valid, so this is only discoverable at run time. Switched to `eleven_flash_v2`.
- **Partial failure handled:** that failed create happened after the tool was created. The tool ID was already saved, so the retry updated the same tool instead of making a duplicate.
- **Idempotent updates:** running `agent.py` again keeps the same tool and agent IDs.
- **API key scope:** the key could list voices and agents but not read the subscription.

## Agent testing API

- **Tool-call parameter paths are undocumented.** A test that checks a webhook tool's body parameters must use the path `body.<name>`. Found by creating six temporary tests with different path styles; only `body.callback_number` passed.
- **Test results expose the tool's secret header.** The test-run response includes the webhook tool's request headers in plain text, including the shared secret. Rotated the secret afterwards. A plain header is not a safe place for a secret; workspace secrets are.
- **The SDK retries HTTP 500 for a long time.** A mocked 500 held a unit test for more than two minutes.
- **Simulated-caller tests work** and were the most useful kind: they caught behaviour that single-turn tests could not.
- **Cost:** five full runs of 13–14 tests plus one six-test probe used about 6,800 credits. A simulation costs roughly ten times a single-reply test (about 390 against about 43).

## Agent behaviour: tuning rounds 1–3

Rounds 1–3: five full test runs. Scores: 11/13, 11/13, 13/14, 13/14, 13/14. After three rounds, one non-safety test still failed per run, a different one each time: `record-check` (correct answer, no source named) and `sim-collision-triage` (right triage, then a callback attempt in place of the Collision Reporting Centre guidance).

1. **Round 1:** the bike-theft test was too strict. The agent asked whether the bike was worth under or over $5,000, which is the real threshold for online reporting in the corpus. Fixed the test, not the agent.
2. **Round 2:** the agent offered a callback for a pizza question, and jumped straight to 911 for "there's someone outside my house" without asking whether anyone was in danger. Changed the prompt for both and added a test for the second.
3. **Round 3:** round 2's wording made the agent ask a follow-up to a caller who said they weren't sure if it was an emergency. Tightened the prompt so caller uncertainty always means 911. The safety test itself was not changed.

## Round 4: repeated runs and a model comparison

After round 3, one non-safety test still failed per run (a different one each time), and reasoning text had leaked into a reply. Round 4 ran every test three times per configuration (42 runs each) and scanned all agent replies for leaked reasoning.

| Configuration | Passed | Leaked-reasoning replies | Credits |
|---|---|---|---|
| Gemini 2.5 Flash, tightened prompt | 42 / 42 | 3 of 67 | 3,888 |
| Claude Haiku 4.5, same prompt | 36 / 42 | 0 | 8,602 |
| GPT-4.1 mini, same prompt | 34 / 42 | 0 | 3,980 |
| Gemini 2.5 Flash, thinking off | 39 / 42 | 0 of 67 | 3,228 |
| **Gemini 2.5 Flash, thinking off, Rule 4 rewritten (final)** | **42 / 42** | **0 of 67** | **3,434** |

- **Prompt changes that fixed the intermittent failures:** every grounded answer must start by naming its source page; once triage is complete the agent must give the guidance and never log a callback in place of an answer.
- **The other models failed safety tests on this prompt.** Claude Haiku 4.5 asked a follow-up to the unsure caller in 3 of 3 runs and missed the callback tool call in 3 of 3; it also cost more than twice as much. GPT-4.1 mini asked a clarifying question during a break-in in progress in 2 of 3 runs. The prompt was tuned on Gemini, so this shows the prompt is model-specific, not that those models are worse in general.
- **Leaked reasoning was Gemini's hidden thinking.** Three replies ended with text such as "According to Rule 1, I must instruct the user…". The tests still passed, because the evaluator did not penalise it. Setting `thinking_budget: 0` removed it and lowered cost. Both simulations now also require that the agent never speaks its reasoning.
- **Turning thinking off exposed a prompt ambiguity.** The agent stopped offering a callback for case-status questions (0 of 3). Rewriting Rule 4 as two separate bullets fixed it.
- **One run is not enough.** A single 14-test run passed several times while a behaviour was failing one time in three. Repeated runs (`repeat_count`) were what made the results trustworthy.

**The three safety tests** (`emergency-in-progress`, `unsure-emergency`, `sim-escalates-to-911`) passed in all 9 of their runs on the final configuration.

**Other things seen:**

- **Wrong source name:** in an early run the agent attributed record-check information to "the online reporting page".
- **Total test credits used so far:** about 31,000.

## Live voice calls

- **False alarm on an unscripted question (6 Oct).** Asked by voice: "Where do I find bullets for my gun?" The agent replied "Please hang up and call 911 now." The question describes no danger; the expected reply was an off-topic or not-covered response. Likely cause: Rule 1 tells the agent to treat anything that "might be describing" a risk as an emergency, and the test suite has no harmless-question-with-an-alarming-word case, so over-triggering was never measured. Left untuned by choice and recorded as a finding. Whether `thinking_budget: 0` contributes is untested.

- **Escalation in the middle of a callback (6 Oct).** While giving the summary for a callback request, the caller said people were using drugs and partying in their backyard. The agent abandoned the callback and said to call 911. Defensible, since it describes something in progress on the caller's property. No automated test covers an emergency raised partway through the callback flow. The webhook-failure path was not reached on this attempt.

- **Scripted call 4, webhook down (6 Oct): worked.** With the webhook server stopped, the agent completed the read-back, the tool call failed, and the agent gave the non-emergency number. No post appeared in Mattermost.
- **Phone numbers are read as grouped numbers (6 Oct).** The agent said "four sixteen" for the 416 area code instead of "four one six". The prompt writes the number as digits (`416-808-2222`), and the fast voice model reads digit groups as numbers. Two available fixes: tell the model in the prompt to write phone numbers one digit at a time, or set the agent's `text_normalisation_type` to `elevenlabs` so the platform normalises numbers before speech. The prompt already does the first for "nine one one", which is why 911 is read correctly. **Applied the prompt fix** the same day: phone numbers are now written out one digit at a time. All 42 repeated test runs still passed and no reply contained a phone number in digit form. The read-back of a caller's own number is not covered by a test transcript, so it needs checking by ear.

- **Scripted calls 1 to 3 (6 Oct):** collision triage, escalation to 911, and a callback with the webhook running all went well enough to use in the demo recording.
- **Phone-number fix confirmed by ear (6 Oct).** Both the fallback number and the read-back of the caller's own number are now spoken one digit at a time.
- **The callback asks the same thing twice (6 Oct).** The agent asked for "a short topic", then for "a one-sentence summary". The caller gave the identical sentence both times. Cause: the tool has separate `topic` and `summary` fields and the prompt tells the agent to collect all four fields one at a time. The agent could derive the topic from the summary itself.
- **Exaggerated rising intonation on a short question (6 Oct).** Heard right after the second summary answer; the transcript shows the agent's line there was "And what is your first name?" Likely a prosody artifact of the fast voice model on very short question turns. Not confirmed, since the tests and transcripts are text only.
- **Demo disclosure came after the tool call, not at read-back (6 Oct).** The prompt asks for it at read-back, before the caller says yes. In this call the agent confirmed the details, logged the callback, and only then said no one would actually call.
- **Callback flow rewritten (6 Oct).** The agent now asks once what the callback is about and writes the topic itself; asks for name and number together; and gives the demonstration notice in the read-back, before the caller confirms. The tool's `topic` field is marked as written by the agent. Added a 15th test, `callback-asks-once`. All 45 repeated runs passed with no leaked reasoning. Whether the intonation improved needs checking by ear.
- **New callback flow confirmed by ear (6 Oct).** One question about the issue, name and number together, demonstration notice before confirming. The Mattermost post carried a sensible topic written by the agent.

- **Demo notice still came after the tool call in the recorded take (6 Oct).** In the call recorded for the video, the read-back did not include the demonstration notice; the agent gave it after logging the callback, alongside the reference code. The earlier check by ear found it in the right place, so the prompt change made this more likely, not certain. The notice is always given; its position varies.
- **The agent skipped the damage question in that take** and gave guidance after two triage questions. Acceptable: it had enough to route.

## Voice clone and narration

- **SDK bug on instant voice clone (6 Oct).** `voices.ivc.create` without `labels` sends the literal string `null` for that field, and the API rejects it with "Labels must be serialized dictionary object". Passing labels as a JSON string double-encodes them and fails the same way. Passing a dict works. The unit test had not caught it because the mock accepted any body.
- **Clone and narration worked first time after that.** A 132-second phone recording produced the clone; six narration clips totalling 102 seconds were generated with `eleven_multilingual_v2`.
- **Pause tags produced a stray spoken sound (6 Oct).** In the privacy clip, the narration says something like "C-T-U" at 15.9 s, where the script has a `<break time="0.7s" />` tag and no words. Confirmed by transcribing the clip with ElevenLabs speech-to-text (Scribe), which returned "…a phone number, CTU. Use zero retention mode…". Five break tags in one 32-second clip; one misfired. Safer approach: generate each point as its own clip and space them on the timeline.
- **Speech-to-text used as a checking tool.** Scribe's word-level timestamps located the artifact to the tenth of a second without listening.
