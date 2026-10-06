# Narration script

Each `##` heading is a file name. Text under it is spoken. Lines starting with `>` are
notes for the edit and are not spoken. Pauses between points come from spacing separate clips on the timeline; pause tags in the text caused a stray spoken sound, so they are not used.

## 01a-problem

Police non-emergency lines spend a lot of their time on routine questions. How do I
report a stolen bike? Where do I get a record check?

> Animated: a ringing non-emergency line, with question bubbles appearing as they are spoken.

## 01b-built

I built a small voice agent on ElevenLabs, with Claude Code as my coding assistant, to
see how much of that it could handle.

> Title. Captions: "Unofficial demo. Not a Toronto Police service." and "Narration: an ElevenLabs clone of my own voice."

## 01c-knowledge

The agent's knowledge is seventeen public pages from the Toronto Police website: how to
report online, collision reporting, record checks, and so on. It's told to answer only
from those pages, and to say which one.

> Animated: the seventeen page titles slide into the knowledge base.

## 02-live-call

Here's a caller who says only that someone hit their car. The agent doesn't guess. It
asks about injuries first, then works through what it needs, and answers from the
published guidance, naming its source. When the caller wants a REAL person, it takes a
callback request, and that lands in the team channel in Mattermost a moment later.

> Play call audio underneath, ducked. Show the widget beside Mattermost.

## 03-safety

The most important behaviour is knowing when to stop. Here the call starts out vague,
and the moment it sounds like someone is in danger, the agent says to hang up and call
nine one one, and does nothing else.

## 04-how-its-built

The knowledge base, the agent, its webhook tool and its tests are all defined in Python
and kept in version control. The tests include simulated callers that hold a whole
conversation. Every test runs three times, because a single passing run turned out to
prove very little. And the first unscripted question I asked it by voice still found a
false alarm that none of those tests had a case for.

> Show config/agent.yaml, then the terminal running agent_tests.py, then the results table.

## 05a-privacy

For organisations with strict privacy requirements, here's what this design gives you to
work with.

> Animated diagram, built up one step per clip: caller, ElevenLabs, your side.

## 05b-public-knowledge

The agent's knowledge is seventeen public web pages. Nothing confidential goes in.

## 05c-callback-fields

A callback sends three things to your systems: a first name, a phone number, and a
one-line summary.

## 05d-zero-retention

Zero retention mode limits what ElevenLabs keeps from each call.

## 05e-residency

Regional data residency keeps stored data in a chosen region, where it's offered.

## 05f-own-model

And for anything sensitive, the model itself can run on your side, so ElevenLabs handles
only the speech.

## 06-close

The code and a one-page write-up are linked below. Thanks for watching.

> Title card with the repo link.
