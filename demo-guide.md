# AI TPM Demo Guide — How I AI

---

## Demo narrative arc

Three acts, ~10 min total:

1. **It watches** — autonomous monitor scanning Jira every hour
2. **It drafts** — contextual nudges and TLU sections, with your voice, not a template
3. **You approve, it acts** — one emoji closes the loop across Slack, Jira, and Notion

---

## Pre-demo: Generate the TLU report

**Before the session starts**, send this message in `#cloudsort_aitpm`:

```
@aitpm generate TLU for last week
```

The bot will:
1. Pull Jira state + any meeting notes from the vault for last week
2. Draft the three TLU sections (Where We Are, Achievements, Risks)
3. Post each section to the channel for approval

**Show in the demo:** the three drafted sections sitting in the channel, ready to approve.

---

## Live demo 1: Run the project monitor

Run this live — takes ~1–2 min:

```bash
cd ~/loka/code/claude-aitpm
python main.py --once monitor
```

**Show:**
- Terminal output as the agent reads Jira state and reasons about the project
- The Slack message it posts to `#cloudsort_aitpm`
- If a nudge draft is posted: this is your moment (see demo 2 below)

**Talking point:** that terminal output is two agents running back-to-back. Haiku scans and detects what needs attention. Sonnet writes the actual message. Hourly scans cost pennies. Sonnet only fires when there's something worth drafting.

---

## Live demo 2: The Jira nudge loop (most impressive E2E)

If the monitor posted a nudge draft, show the full loop:

1. **Bot posts draft to Slack** — "CLOUD-42 has been in-progress 12 days. Proposed comment: ..."
2. **React ✅** — one emoji, no other action
3. **Bot posts the comment to Jira** — confirms in-thread "✅ Comment posted on CLOUD-42"

You never opened Jira. The bot wrote it, you approved it, it landed.

**Bonus — show the edit flow:**
Instead of ✅, reply: _"make it more direct, less polite"_
Bot revises in-thread. React ✅ to the revision. Same result, your voice.

---

## Live demo 3: TLU section-by-section approval

Show the pre-generated TLU sections in the channel. Walk through:

1. **Three sections, three approval moments** — Where We Are, Achievements, Risks
2. **React ✅ on the first section** — bot confirms "✅ Pushed to Notion: Where We Are"
3. Ask: _what if you disagree with something?_ Reply with an edit request in-thread. Bot revises, you approve the revision.
4. Approve the remaining two sections → "TLU for week of ... fully published to Notion."

**Talking point:** the bot knows the TLU writing template. It's not summarizing Jira — it's writing in a specific format with your voice. You're the editor, not the author.

---

## Live demo 4: Command in-thread (natural language over Jira)

Reply to any alert or draft in the channel with a question:

> _"what's actually blocking this?"_

> _"who owns CLOUD-55 right now?"_

> _"is this risk already captured in the TLU?"_

Bot answers in-thread using live Jira context. No context switching, no opening Jira tabs.

---

## Key talking points

- **Human in the loop** — nothing goes out without your approval. React ✅ or reply to edit. You can never unknowingly publish something.
- **Reads real context** — Jira tickets, comments, assignees, durations. Not generic summaries.
- **Two-phase, two-model** — cheap model detects what needs attention, smarter model writes the message. Cost scales with signal, not with time.
- **Runs fully autonomous** — `python3 main.py` and walk away. Monitor every hour, poll for your approvals every 3 min. One process, no infra.
- **Cross-system action** — one ✅ in Slack can write a Jira comment, push a Notion page, or post to another Slack channel. The approval is the interface.

---

## What NOT to show

- The config YAML files — too in-the-weeds for a demo, kills momentum
- The state JSON — same
- Error cases or retries — unless they happen naturally and you can narrate through them
