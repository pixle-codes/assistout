# assistout

**Find every OpenAI Assistants API landmine in your codebase before it detonates.**

The Assistants API (Assistants, Threads, Messages, Runs, Run Steps) was removed
from the OpenAI API on **2026-08-26** — endpoints gone entirely, no read-only
period ([official notice](https://developers.openai.com/api/docs/deprecations)).
OpenAI ships a prose migration guide but states plainly:
*"We will not provide an automated tool for migrating Threads to Conversations."*

`assistout` is the missing tool: a deterministic, offline, zero-dependency
scanner that inventories your Assistants API usage, maps each finding to its
Responses/Conversations replacement with a concrete before → after rewrite
hint, triages each one by migration effort (`mechanical` / `moderate` /
`manual`) so you know what's a find-and-replace versus an event-loop redesign,
emits SARIF for pull-request annotations, and offers `--emit-backfill`, which
generates the Threads→Conversations history-migration script OpenAI declined
to provide.

It also covers the **Microsoft second wave**: Azure OpenAI resources serve the
same Assistants surface at `/openai/threads*` / `/openai/assistants*` and it
dies the same day (2026-08-26), while code on the **Foundry Agent Service
(classic)** SDK (`project.agents.create_agent / threads / messages / runs`,
retiring **2027-03-31**) gets its own findings, deadline line, and migration
map to `create_version(PromptAgentDefinition)` + conversations/responses.

And as of v0.5.0, the **third wave**: reusable **prompt objects** (dashboard
Prompts, served by `v1/prompts`) shut down on **2026-11-30**
([deprecations page](https://developers.openai.com/api/docs/deprecations#2026-06-03-reusable-prompts)).
This is a trap for Assistants migrators — earlier migration guides pointed
people at dashboard Prompts as the replacement, so teams that followed them
now face a *second* forced migration 96 days later. assistout flags `pmpt_…`
ids, `prompt={...}` parameters, `.prompts.*` SDK calls, `/v1/prompts` REST
calls — and its Assistants guidance now steers you to inline prompts in code
(the official post-prompt-object path), never into another managed store.

## What it detects

| Category | Example | Replacement | Effort |
|---|---|---|---|
| `thread_crud` | `client.beta.threads.create()` | `client.conversations.create()` | mechanical |
| `thread_messages` | `client.beta.threads.messages.list(...)` | `conversations.items` (+ [official backfill recipe](https://developers.openai.com/api/docs/assistants/migration)) | moderate |
| `runs` | `client.beta.threads.runs.create/retrieve/poll(...)` | `responses.create(conversation=..., input=[...])`; polling loops deleted | manual |
| `run_steps` | `client.beta.threads.runs.steps.list(...)` | iterate `response.output[]` items | manual |
| `streaming` | `.runs.stream(...)`, `AssistantEventHandler` | Responses streaming events / `background=True` | manual |
| `assistant_objects` | `client.beta.assistants.create(...)` | inline model+instructions+tools at each `responses.create` — **not** dashboard Prompts (they die 2026-11-30 too) | manual |
| `vector_stores` | `client.beta.vector_stores.files.upload(...)` | survives — re-attach via `tools=[{"type": "file_search", ...}]` | moderate |
| `assistant_refs` | `"asst_8fVY..."`, `OPENAI_ASSISTANT_ID` | inline the bundle in code; drop the id indirection | moderate |
| `js_run_helpers` | `.runs.createAndPoll(...)`, `.runs.createAndStream(...)` | awaited `responses.create` / Responses stream events | manual |
| `assistant_id_arg` | `assistant_id="asst_..."` at any call site | inline the assistant's model/instructions/tools on `responses.create` | moderate |
| `http_endpoints` | `fetch("https://api.openai.com/v1/threads/...")` | `/v1/conversations` + `/v1/responses` | manual |
| `prompt_object_refs` ⏰ | `"pmpt_abc123"`, `OPENAI_PROMPT_ID`, `prompt_id:` | move the stored prompt's text into code (`input=[...]`) — dead **2026-11-30** | mechanical |
| `prompt_sdk_calls` ⏰ | `client.prompts.retrieve/create/list/delete(...)` | keep prompts in your repo, pass text inline | manual |
| `prompt_param` ⏰ | `responses.create(prompt={"prompt_id": pid, ...})`, JSON/TS `prompt: {...}` | build messages in code and pass as `input`; variables become function args | moderate |
| `http_endpoints` ⏰ | `GET /v1/prompts/pmpt_...` | no API successor — read prompt content from your repo | mechanical |

⏰ = own deadline (**2026-11-30**), rendered as a separate countdown line when
such findings exist.
| `foundry_create_agent` | `project.agents.create_agent(...)` (py) / `agents.createAgent(...)` (js) | `create_version(agent_name, PromptAgentDefinition(...))` — retires 2027-03-31 | moderate |
| `foundry_threads` | `project.agents.threads.create(...)` / `agents.createThread(...)` | `openai.conversations.create(...)` via `get_openai_client()` | moderate |
| `foundry_messages` | `project.agents.messages.create/list(...)` / `createMessage/listMessages` | `openai.conversations.items.*` | moderate |
| `foundry_runs` | `project.agents.runs.create/get(...)` / `createRun/getRun` | `openai.responses.create(conversation, agent_reference)` | manual |
| `foundry_run_process` | `project.agents.runs.create_and_process(...)` | single `responses.create` + `extra_body={"agent_reference": ...}`; polling loop deleted | manual |
| `azure_http_endpoints` | `POST https://myres.openai.azure.com/openai/threads?api-version=...` | `/openai/v1/conversations` + `/openai/v1/responses` — dead 2026-08-26 like OpenAI's | manual |

SDK method calls are detected in Python **and** JavaScript/TypeScript sources
(`.js .jsx .ts .tsx .mjs .cjs`); raw REST endpoint strings and hardcoded ids are
detected in **every** text file (Go, YAML, Terraform, .env, ...). New-style
Foundry code (`create_version`, `PromptAgentDefinition`, `get_openai_client()`,
`responses/conversations`) is deliberately **not** flagged.

## Install

No dependencies beyond Python 3.10+:

```bash
git clone https://github.com/pixle-codes/assistout.git
cd assistout
python3 -m assistout path/to/your/project
```

Or copy the `assistout/` package directory into your repo/tooling.

## Usage

Every finding ships with a **before → after rewrite hint** — a concrete
snippet pair showing the migration, so you're never left staring at a category
name:

```console
$ python3 -m assistout ~/code/my-agent-app

assistout v0.3.0 — Assistants API migration scanner
OpenAI Assistants API shuts down 2026-08-26 — 3 days left

src/chat.py
  L24   moderate   thread_messages   .beta.threads.messages.create
        - client.beta.threads.messages.create(tid, role="user", content="hi")
        + client.conversations.items.create(cid, items=[{"type": "message", "role": "user", "content": "hi"}])
  L27   manual     runs              .beta.threads.runs.create
        - run = client.beta.threads.runs.create(thread_id=tid, assistant_id=aid)
        + res = client.responses.create(conversation=cid, input=items) # bundle inlined as model/instructions/tools args
  L29   manual     runs              .beta.threads.runs.retrieve
  L30   manual     run_steps         .beta.threads.runs.steps.
        - steps = client.beta.threads.runs.steps.list(thread_id=tid, run_id=rid)
        + for item in response.output: ...  # messages/tool calls are output items
Summary: 4 finding(s) across 1 file(s); 12 file(s) scanned
  by category: runs x2, thread_messages x1, run_steps x1
  by effort:   manual: 3, moderate: 1

Migration map: threads->conversations, runs->responses.create,
assistants->dashboard prompts, run steps->output items.
```

(Identical consecutive hints are printed once per run of findings — L29 above
reuses L27's hint without re-printing it.)

Machine-readable mode for scripts and CI:

```console
$ python3 -m assistout src --json | jq '.totals'
{
  "findings": 4,
  "by_category": { "runs": 2, "thread_messages": 1, "run_steps": 1 },
  "by_effort": { "manual": 3, "moderate": 1 }
}
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | scanned clean — no Assistants API usage |
| 1 | findings present |
| 2 | unreadable/no files at the given path |

Gate a release branch: `python3 -m assistout . || echo "still has Assistants usage"`.

### SARIF output — surface findings as PR annotations

`--sarif OUT` writes [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html)
(exit codes unchanged; `-` means stdout). Effort levels map to SARIF severities:
`manual`→error, `moderate`→warning, `mechanical`→note.

Upload it with GitHub code scanning and every finding becomes an inline
annotation on the exact line:

```yaml
# .github/workflows/assistants-deadline.yml
name: assistants-api-deadline-check
on: [push, pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.x" }
      - name: Clone assistout (zero-dependency)
        run: git clone --depth 1 https://github.com/pixle-codes/assistout.git /tmp/assistout
      - name: Scan for Assistants API usage
        run: python3 /tmp/assistout/assistout . --sarif assistout.sarif || true
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: assistout.sarif
```

Results carry stable `partialFingerprints`, so alerts dedupe across pushes
instead of re-opening on every commit.

### The backfill generator — save your thread history before Aug 26

OpenAI ships **no** Threads→Conversations migration tool. `--emit-backfill`
writes you one: a standalone script implementing the
[official recipe](https://developers.openai.com/api/docs/assistants/migration)
(`threads.messages.list` → `conversations.create`) plus the production
properties the docs leave to you:

```console
$ python3 -m assistout --emit-backfill backfill_conversations.py
wrote backfill_conversations.py (179 lines). Run it with your thread IDs
BEFORE 2026-08-26; see --help inside the script.

$ python3 backfill_conversations.py thr_abc123 thr_def456 --metadata team=core
ok thr_abc123 -> conv_9xK... (42 items)
ok thr_def456 -> conv_7yL... (8 items)

$ cat backfill_map.jsonl     # idempotency journal — re-runs skip mapped threads
thr_abc123	conv_9xK...
thr_def456	conv_7yL...
```

What it adds beyond the docs' snippet:
- **Idempotency journal**: each success appends `thread_id→conversation_id`;
  crash mid-batch and re-run without creating duplicates.
- **Fail-visible content policy**: unsupported content parts (`image_file`,
  code-interpreter outputs, ...) abort the thread by default; `--allow-lossy`
  drops them *explicitly* and logs exactly what was lost. Nothing disappears
  silently.
- **Dry-run mode**, custom `--metadata`, ids from argv or `$ASSISTOUT_THREAD_IDS`.
- **Deadline-aware**: warns if run at/after 2026-08-26.

Requires only the `openai` SDK and stdlib. Run it once per environment before
the shutdown; after it, thread history is unreadable everywhere.

## How it works

Rules are ordered by specificity and matches claim their character span, so
`.beta.threads.runs.steps.list` is classified once as `run_steps` rather than
also matching the generic `runs` rule. Python-targeted rules run only on `.py`
files; "any file" rules (raw endpoints, id patterns) run everywhere. Binary
files (NUL sniff) and files over 2 MB are skipped; VCS/build directories
(`node_modules`, `.git`, `__pycache__`, ...) are pruned during the walk.

The countdown line tracks the real shutdown date and flips to
*"endpoints are gone, migration is mandatory"* after 2026-08-26 — post-deadline
scans are exactly when stragglers need this most. When Foundry classic-agent
findings are present, a second line counts down to their separate 2027-03-31
retirement, so mixed workloads can't confuse one deadline for the other.

## Design stance

- **Offline and private**: static analysis of local files. Nothing is uploaded;
  no LLM interprets your code.
- **Deterministic**: same input, same findings — suitable for CI gates.
- **Opinionated effort labels**: `mechanical` means near find-replace;
  `manual` means redesign (polling loops, streaming handlers). Labels come from
  the official migration guide's own examples.

## Roadmap

- [x] **M2** (v0.2): `--emit-backfill` generating the official
  threads→conversations backfill script; JS/TS SDK-call detection.
- [x] **M3** (v0.3): per-finding before/after rewrite hints in human + JSON
  reports; `--sarif` output with stable fingerprints for GitHub code scanning.
- [x] **M4** (v0.4): Microsoft second wave — Foundry Agent Service (classic)
  SDK shapes (retire 2027-03-31) and Azure `/openai/threads|assistants` HTTP
  calls (dead 2026-08-26), each finding tagged with its own deadline.
- [x] **M4.5** (v0.5): third wave — reusable prompt objects (`v1/prompts`,
  dashboard Prompts) shut down **2026-11-30**; `pmpt_` ids, `prompt={...}`
  params, `.prompts.*` SDK calls and `/v1/prompts` REST calls detected with
  their own countdown; Assistants migration guidance rewritten so it no
  longer steers people into prompt objects (the double-migration trap).
- **M5 (only on demand)**: PyPI packaging.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Test coverage pins the rule-priority contract (run-steps and JS helpers beat
generic runs, streaming beats runs), the per-language rule split (py vs js vs
any file), binary/large-file skips, the JSON schema, hint rendering and
consecutive-duplicate suppression, SARIF structure/levels/fingerprints,
countdown wording around the shutdown date, all exit codes — and the emitted
backfill script's real behavior, executed offline against a fake SDK (paging,
journal idempotency, dry-run, lossy-content policy).

## License

MIT — see [LICENSE](LICENSE).
