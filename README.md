# assistout

**Find every OpenAI Assistants API landmine in your codebase before it detonates.**

The Assistants API (Assistants, Threads, Messages, Runs, Run Steps) was removed
from the OpenAI API on **2026-08-26** — endpoints gone entirely, no read-only
period ([official notice](https://developers.openai.com/api/docs/deprecations)).
OpenAI ships a prose migration guide but states plainly:
*"We will not provide an automated tool for migrating Threads to Conversations."*

`assistout` is that missing tool's first half: a deterministic, offline,
zero-dependency scanner that inventories your Assistants API usage, maps each
finding to its Responses/Conversations replacement, and triages each one by
migration effort (`mechanical` / `moderate` / `manual`) so you know what's a
find-and-replace versus an event-loop redesign.

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
| `http_endpoints` | `fetch("https://api.openai.com/v1/threads/...")` | `/v1/conversations` + `/v1/responses` | manual |

SDK method calls are detected in Python sources; raw REST endpoint strings and
hardcoded ids are detected in **every** text file (JS, TS, Go, YAML, .env, ...).

## Install

No dependencies beyond Python 3.10+:

```bash
git clone https://github.com/OWNER/assistout.git
cd assistout
python3 -m assistout path/to/your/project
```

Or copy the `assistout/` package directory into your repo/tooling.

## Usage

```console
$ python3 -m assistout ~/code/my-agent-app

assistout v0.1.0 — Assistants API migration scanner
OpenAI Assistants API shuts down 2026-08-26 — 3 days left

src/chat.py
  L24   moderate   thread_messages   .beta.threads.messages.create
  L27   manual     runs              .beta.threads.runs.create
  L29   manual     runs              .beta.threads.runs.retrieve
  L30   manual     run_steps         .beta.threads.runs.steps.
Summary: 4 finding(s) across 1 file(s); 12 file(s) scanned
  by category: runs x2, thread_messages x1, run_steps x1
  by effort:   manual: 3, moderate: 1

Migration map: threads->conversations, runs->responses.create,
assistants->dashboard prompts, run steps->output items.
```

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

- **M2**: `--emit-backfill` generating the official threads→conversations export
  script parameterized per project; JS/TS SDK-call detection.
- **M3**: per-finding before/after rewrite hints, SARIF output for GitHub code
  scanning annotations.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Test coverage pins the rule-priority contract (run-steps beats runs, streaming
beats runs), the Python-vs-any-file rule split, binary/large-file skips, the
JSON schema, countdown wording around the shutdown date, and all exit codes.

## License

MIT — see [LICENSE](LICENSE).
