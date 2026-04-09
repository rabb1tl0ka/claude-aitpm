# Idea: Reply to any bot message to trigger an action

## What's the idea

Any message posted by the AI TPM bot in Slack — alerts and drafts alike — becomes an actionable thread. Bruno can reply with a free-form instruction and the bot acts on it, without needing to prefix with `@aitpm`.

Example:
> Bot: "CLOUD-6561: moved to In Review. Good progress on payments onboarding flow."
> Bruno replies: "great! post a comment on Jira saying good job"
> Bot: posts the comment on CLOUD-6561 and confirms in thread.

## Expected advantages / benefits

- Natural UX — every bot message is a conversation, not a one-way notification
- No need to remember `@aitpm` syntax for follow-up actions on specific tickets
- Keeps context in the thread — the ticket key and context are already there, Bruno just adds intent
- Alerts become actionable without being redesigned as drafts

## Downsides / risks

- Increases poll complexity — currently the poll distinguishes draft vs alert by type; free-form replies on alerts need a different handling path
- Risk of accidental triggers — Bruno replies to a thread for another reason, bot misinterprets as an instruction
- Each free-form reply on an alert would spawn a `run_command` agent call (~1,000-2,000 tokens) — cost scales with reply volume

## What's been tried already

Nothing yet. Currently:
- Replies to **draft** messages → handled by intent detection (approve/discard/edit)
- Replies to **alert** messages → poll detects them but has no action to execute
- `@aitpm` commands → reliable path for free-form instructions, but requires knowing the syntax

## Open questions

1. How does the bot distinguish "Bruno giving an instruction" from "Bruno replying for another reason" in an alert thread?
2. Should free-form replies on alerts always route to `run_command`, or should common patterns (approve, discard) still use the fast intent detection path?
3. Should the bot confirm before acting on a free-form reply, or act immediately and confirm after?
