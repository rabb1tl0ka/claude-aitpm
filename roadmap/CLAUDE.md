# Roadmap Convention

This repo uses a `roadmap/` directory to track features, ideas, and challenges.

## Directory structure

```
roadmap/
  feat-name/              ← workspace item (spec + supporting material)
    feat-name.md
    docs/
  idea-simple.md          ← flat item (no workspace needed)
  archived/               ← completed or abandoned items (omitted from table)
  templates/
  README.md
  CLAUDE.md
```

Every roadmap entry is either:
- A **flat `.md` file** — simple items with no supporting material
- A **workspace directory** — items with a spec file + `docs/` for research, references, and artifacts

## File naming

Every roadmap entry uses one of three prefixes:
- `feat-` — fully specced feature, ready to implement
- `idea-` — early exploration, not yet fully designed
- `challenge-` — known problem, solution still open

## Reviewing specs

Use `[YourName: your comment]` to annotate specs inline. Claude Code will recognize these as reviewer comments when asked to review them.

## Roadmap Management Rules (Strict - Always Follow)

You are the active maintainer of the roadmap in the `roadmap/` directory.

### Frontmatter (minimal)
Every roadmap file must start with this exact frontmatter block:

---
status: todo | in-progress | done | blocked | review
priority: high | medium | low
owner: ""
---

- Default new items to `status: todo`, `priority: medium`, and `owner: ""`
- When someone picks up an item, set `status: in-progress` and `owner: <handle>` (e.g. `@rabb1tl0ka`, `@claude-code`)
- Update `status`, `priority`, and `owner` whenever you or the user changes the state of an item.
- Never remove the frontmatter once added.

### One-Line Overview
Every file must have a `## One-Line Overview` section right after the main title.
- It must be **one single, crisp sentence**.
- It should cohesively describe the problem-solution space (not just the goal).
- Keep it concise, high-signal, and useful for the overview table.

### When asked to save a feature, idea, or challenge

1. Use the matching template from `roadmap/templates/template-feat.md`, `roadmap/templates/template-idea.md`, or `roadmap/templates/template-challenge.md`
2. Create as a **workspace directory**:
   - `mkdir roadmap/<prefix>-<slug>/`
   - Create `roadmap/<prefix>-<slug>/<prefix>-<slug>.md` from the template
   - Create `roadmap/<prefix>-<slug>/docs/` (always auto-create this)
3. Add a row to the `## Current roadmap` table in `roadmap/README.md`

### Promotion (flat → workspace)

When a user asks to create a `docs/` directory for a flat item, auto-promote it:
1. Create `roadmap/<prefix>-<slug>/` directory
2. Move `roadmap/<prefix>-<slug>.md` into it
3. Create `roadmap/<prefix>-<slug>/docs/`
4. Update the table link to point to the subdir spec

### When asked to load or work on a roadmap entry

Read the relevant file in full before starting — branch name, implementation steps, test plan, and open questions are all in there. Present a plan and wait for explicit approval before writing any code.

### When asked to archive an item

When marking an item as done or explicitly archiving:
1. Update `status: done` in the spec file
2. Move the entire item (file or directory) to `roadmap/archived/`
3. Remove from the active table in `roadmap/README.md`

### Automatic Table Maintenance
After **any** of the following actions, you **must** regenerate the entire "Current roadmap" table in `roadmap/README.md`:

- Creating a new `feat-`, `idea-`, or `challenge-` file or workspace
- Updating status, priority, or the One-Line Overview of any roadmap file
- Marking something as done, in-progress, blocked, etc.
- Archiving, deleting, or renaming a roadmap item

**How to generate the table:**
1. Scan `roadmap/` for entries matching `feat-*`, `idea-*`, `challenge-*`:
   - If it's a `.md` file → parse directly
   - If it's a directory → look for `<dirname>.md` inside it (e.g. `roadmap/feat-name/feat-name.md`)
   - Skip anything inside `roadmap/archived/`
2. Parse the frontmatter for status and priority
3. Extract the exact text from the `## One-Line Overview` section
4. Build the markdown table with these columns:
   - File (flat: `[feat-name.md](feat-name.md)` / workspace: `[feat-name/](feat-name/feat-name.md)`)
   - Status (use emojis: ✅ done, 🚧 in-progress, ⏳ todo, ❌ blocked, 🔍 review)
   - Priority
   - Owner (empty string if unset)
   - One-Line Overview
5. Sort the table by: type (feat → idea → challenge), then priority (high → medium → low), then filename
6. Place the new table under the "## Current roadmap" heading. Keep the note: "(The table above is automatically maintained by Claude Code. Do not edit it manually.)"

### Useful Commands You Should Recognize
- "Update roadmap table" → Regenerate the full table now
- "Show roadmap" or "Show current roadmap" → Print a nicely formatted summary grouped by type
- "Mark [filename] as done/in-progress/blocked" → Update frontmatter + refresh table
- "Set priority of [filename] to high/medium/low" → Update + refresh table
- "Pick [filename]" or "I'm picking [filename]" → Set `status: in-progress` + `owner: <handle>` + refresh table
- "Archive [item]" → Mark done, move to `roadmap/archived/`, remove from table

When the user asks you to create a new feature, idea, or challenge, always:
1. Create the workspace directory and spec file using the correct template
2. Create `docs/` inside the workspace
3. Fill in a strong One-Line Overview
4. Add the frontmatter
5. Immediately update the central table
