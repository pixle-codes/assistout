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

## What it detects

| Category | Example | Replacement | Effort |
|---|---|---|---|
| `thread_crud` | `client.beta.threads.create()` | `client.conversations.create()` | mechanical |
| `thread_messages` | `client.beta.threads.messages.list(...)` | `conversations.items` (+ [official backfill recipe](https://developers.openai.com/api/docs/assistants/migration)) | moderate |
| `runs` | `client.beta.threads.runs.create/retrieve/poll(...)` | `responses.create(conversation=..., input=[...])`; polling loops deleted | manual |
| `run_steps` | `client.beta.threads.runs.steps.list(...)` | iterate `response.output[]` items | manual |
| `streaming` | `.runs.stream(...)`, `AssistantEventHandler` | Responses streaming events / `background=True` | manual |
| `assistant_objects` | `client.beta.assistants.create(...)` | dashboard Prompts, `prompt={"id": ...}` | manual |
| `vector_stores` | `client.beta.vector_stores.files.upload(...)` | survives — re-attach via `tools=[{"type": "file_search", ...}]` | moderate |
| `assistant_refs` | `"asst_8fVY..."`, `OPENAI_ASSISTANT_ID` | swap for prompt id after recreating bundle | moderate |
| `js_run_helpers` | `.runs.createAndPoll(...)`, `.runs.createAndStream(...)` | awaited `responses.create` / Responses stream events | manual |
| `assistant_id_arg` | `assistant_id="asst_..."` at any call site | `prompt={"id": ...}` on `responses.create` | moderate |
| `http_endpoints` | `fetch("https://api.openai.com/v1/threads/...")` | `/v1/conversations` + `/v1/responses` | manual |

SDK method calls are detected in Python **and** JavaScript/TypeScript sources
(`.js .jsx .ts .tsx .mjs .cjs`); raw REST endpoint strings and hardcoded ids are
detected in **every** text file (Go, YAML, .env, ...).

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
        + res = client.responses.create(conversation=cid, prompt={"id": pid}, input=items)
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
scans are exactly when stragglers need this most.

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
- **M4 (only on demand)**: PyPI packaging.

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
