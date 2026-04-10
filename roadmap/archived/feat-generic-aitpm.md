# Feature Spec: Generic AI TPM (de-Bruno-ification)

## Branch

`feat/generic-aitpm`

## Goal

Remove all hardcoded references to Bruno, CloudSort, and `cloudsort.atlassian.net` from agent prompts, comments, and logic. Every identity-specific value becomes a config key or is derived from existing env vars. A new user should be able to point this at their project by editing `configs/their-project.yaml` and setting env vars — nothing else.

This is a prerequisite for the Team AI TPM feature.

---

## Audit: what's hardcoded today

### `src/agents.py` — the bulk of the work

| Line(s) | Hardcoded value | Replace with |
|---------|----------------|--------------|
| 249, 355, 421, 532 | `"for CloudSort"` in agent persona | `cfg['project_name']` |
| 205, 220, 228, 281, 282, 290, 307, 351, 363, 367, 421, 441, 444, 450, 453, 579, 597 | `"Bruno"` | `cfg['tpm_name']` |
| 203, 226, 285, 307, 588, 598, 609 | `https://cloudsort.atlassian.net/browse/` | `{atlassian_browse_url}/` (derived from `ATLASSIAN_SITE` env var) |
| 227 | `CLOUD-6521` example key | `{cfg['jira_project_key']}-XXXX` |
| 588 | `CLOUD-6427` example key | `{cfg['jira_project_key']}-XXXX` |
| 501 | `The cloudId is: cloudsort.atlassian.net` | `The cloudId is: {atlassian_site}` (from `ATLASSIAN_SITE` env var) |

### `src/slack_client.py`

| Line | Hardcoded value | Fix |
|------|----------------|-----|
| 117 | `"Bruno's reply"` in comment | Rename to `"owner's reply"` |

### `main.py`

| Line(s) | Hardcoded value | Fix |
|---------|----------------|-----|
| 185, 237, 272 | `"Bruno"` in comments | Rename to `"owner"` |

### `configs/cloudsort.yaml`

No changes needed — the file is already project-specific by design. The new `tpm_name` key gets added here.

---

## Config changes

Add two new keys to `configs/cloudsort.yaml` (and document in `configs/example.yaml`):

```yaml
tpm_name: "Bruno"              # Human PM's display name — used in first-person nudge comments and approval context
aittpm_name: "Bruno AI TPM"   # Bot identity — used in agent persona, Slack replies, log labels
```

These are independent. `aittpm_name` is not derived from `tpm_name` — each PM can name their digital twin freely.

`atlassian_base_url` is NOT added to config — it's constructed in code from the existing `ATLASSIAN_SITE` env var:

```python
atlassian_browse_url = f"https://{os.environ['ATLASSIAN_SITE']}/browse"
```

---

## Implementation

### Step 1 — New helper in `src/agents.py`

Add at the top of the module, after imports:

```python
def _atlassian_browse_url() -> str:
    return f"https://{os.environ['ATLASSIAN_SITE']}/browse"
```

Used wherever ticket URLs are constructed in prompts.

### Step 2 — Thread `cfg['tpm_name']`, `cfg['aittpm_name']`, and `atlassian_browse_url` into all affected prompts

Each affected function (`run_monitor`, `run_revision`, `run_command`, `run_nudge_drafter`, `run_jira_comment`) resolves these at the top of the function body:

```python
tpm_name = cfg.get("tpm_name", "the PM")
aittpm_name = cfg.get("aittpm_name", "AI TPM")
atlassian_url = _atlassian_browse_url()
```

Replacement rules:
- `"for CloudSort"` in persona → `f"for {cfg['project_name']}"` 
- `"You are the AI AITPM"` → `f"You are {aittpm_name}"`
- `"Bruno"` in approval/command context → `tpm_name`
- `"Bruno"` in nudge drafting rules → `tpm_name`
- Hardcoded Atlassian URLs → `atlassian_url`

### Step 3 — Fix comments in `slack_client.py` and `main.py`

Rename `"Bruno"` → `tpm_name` where it appears in user-visible strings; rename to `"owner"` in pure code comments. No behaviour change.

### Step 4 — Add `configs/example.yaml`

A fully documented template config that a new user can copy and fill in. Documents every key with inline comments. Does not contain any CloudSort-specific values.

---

## What does NOT change

- The `configs/cloudsort.yaml` file itself stays as-is (it's intentionally project-specific)
- `state.py` `user_map` default — this is a runtime-discovered map, not a hardcoded identity. Already generic.
- `owner_slack_user_id` key name in config — already generic
- Env var names (`ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`, `ATLASSIAN_SITE`) — already generic

---

## Definition of done

- `grep -r "Bruno\|CloudSort\|cloudsort\.atlassian" src/` returns zero matches
- A new `configs/example.yaml` exists with no CloudSort-specific values
- Existing CloudSort behaviour unchanged — all values still resolve correctly from config/env
