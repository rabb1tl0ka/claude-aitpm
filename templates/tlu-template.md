# TLU Writing Template

> Loka TPM division-wide standard. Used by AI TPM agents to generate and revise weekly Traffic Light Updates.

---

## Structure

Every TLU has exactly four sections, in this order:

1. **Where We Are**
2. **Achievements**
3. **Risks**
4. **Blockers** *(omit entirely if no active blockers)*

Start with a status line:

```
🟢 Green / 🟡 Yellow / 🔴 Red — [one-line headline]
```

---

## Section: Where We Are

**Format:** 2–4 paragraphs of prose.

**What to cover:**
- Overall sprint/week status
- What was delivered vs. what wasn't
- What's coming next
- Anything that shifted the plan and why

**Voice rules:**
- Business-focused — lead with what it means for the project, not with ticket IDs
- Direct and specific — no filler phrases like "we continued to make progress"
- Reference JIRA keys only to support a point, never as the main content
- No em dashes (—)

---

## Section: Achievements

**Format:** One bullet per achievement.

```
🏆 **[Title - STATUS]** - [One sentence: what was delivered and why it matters. Business impact first.]
```

**Rules:**
- STATUS is typically DELIVERED, DONE, MERGED, RELEASED, or SHIPPED
- Only include things actually completed, merged, or live — no "in progress" achievements
- Prioritise features and high-priority blocker resolutions over minor tasks
- One sentence per bullet — no sub-bullets, no paragraph explanations

**Example:**
```
🏆 **Supplier payment method - DELIVERED** - Suppliers can add a payment method (ACH or credit card) and are gated from publishing capacity without one. The enforcement logic is live.
```

---

## Section: Risks

**Format:** One subsection per active risk.

```
⚠️ Risk #N: [1-line description of what's at risk] (Probability: low/medium/high, Impact: low/medium/high)
[Narrative paragraph: what it is, why it matters for the project. No ticket bullet lists.]
🗣️ CTA #N: [Mitigation owner and target date]
```

**Rules:**
- Narrative paragraph only — no bullet lists of ticket statuses inside a risk
- Probability and Impact must be explicitly stated
- CTA must name an owner and a date
- Risks are about uncertainty and what could go wrong — not about things already blocked

---

## Section: Blockers

**Format:** One subsection per active blocker. Omit this section entirely if there are none.

```
🚨 Blocker #N: [1-line describing what's blocking what]
Impact: [low/medium/high — what cannot progress until resolved]
🗣️ CTA #N: [Owner and target date]
```

**Rules:**
- A blocker is something that has already stopped progress — not a risk that might
- Impact line is required
- CTA must name an owner and a date

---

## General Rules

- **No em dashes** — use commas, colons, or rewrite the sentence
- **No ticket-ID-as-content** — "CLOUD-123 is in progress" is not a TLU statement
- **No corporate speak** — avoid "synergies", "leveraging", "action items", "touch base"
- **No bullet lists inside Where We Are or Risks** — use prose
- **Match the tone of prior TLUs** if format reference examples are provided
