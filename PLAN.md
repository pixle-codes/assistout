# assistout — OpenAI Assistants API migration scanner

## Problem
The OpenAI Assistants API (Assistants, Threads, Messages, Runs, Run Steps)
hard-shuts-down on **2026-08-26** — endpoints removed entirely, no read-only
period ([official deprecations page](https://developers.openai.com/api/docs/deprecations),
announced 2025-08-26 with a 12-month window). Thousands of production apps were
built on it since March 2024 (it was THE batteries-included agent API: threads,
runs, code interpreter, file search).

Who hurts, how badly:
- Every maintainer who didn't finish migrating: hard breakage on Aug 26, and a
  months-long remediation tail as breakage is discovered in prod.
- The official migration guide is prose + one backfill snippet. The docs say it
  outright: **"We will not provide an automated tool for migrating Threads to
  Conversations"** (developers.openai.com/api/docs/assistants/migration).
- Third-party trackers (agentdeals.dev/shutdowns, legittool.com) flag it as the
  #1 imminent developer-facing shutdown; LegitTool notes "no automated tool".

## Why existing solutions fail
- **OpenAI migration guide**: manual reading; no codebase awareness; explicitly
  ships no automation.
- **Consultant lead-gen repos** (e.g. `loyyyygg/assistants-api-migration-rescue`,
  ★0): heuristic scanners that gate you into paid fixed-price migration.
- **Notebook-specific helpers** (`pawarbi/ranch-fabric-data-agent-migrator`, ★0):
  single-vendor single-context.
- Generic codemod frameworks (ts-morph etc.): no Assistants→Responses knowledge
  encoded anywhere.

Verified 2026-08-23 via `gh search repos`: no tool with any stars exists for
this migration.

## Your edge
- **Deterministic, offline, private**: static scan of your repo (no code sent
  anywhere, no LLM in the loop), zero dependencies, stdlib-only Python.
- **Encodes the real mapping table** from the official guide:
  Assistant→dashboard Prompt (`prompt={"id":...}`), Thread→Conversation,
  Runs→`responses.create(conversation=...)`, Run steps→output items, plus the
  nuance that vector stores survive but their wiring changes.
- **Effort triage per finding**: `mechanical | moderate | manual`, so teams know
  what's a find-replace vs. an event-loop redesign before Tuesday.
- **Deadline-aware output**: counts down to shutdown; after Aug 26 the message
  flips to "migration is now mandatory".
- Agent/script friendly: `--json`, exit codes (0 clean / 1 findings / 2 error).

## Architecture
- `assistout/knowledge.py` — ordered detection rules (priority matters:
  run-steps & streaming before generic runs), each rule → category, replacement,
  effort, note. HTTP substring rules apply to every text file (catches raw
  REST calls in any language); SDK regexes run on Python sources.
- `assistout/scanner.py` — file walker (skips VCS/build junk, >2MB files,
  NUL-sniffed binaries), span-claiming match dedupe so overlapping calls
  classify once under the highest-priority rule.
- `assistout/report.py` — human report grouped by file + totals + countdown;
  JSON payload with stable schema.
- `assistout/cli.py` / `__main__.py` — argparse; PATH file-or-dir;
  `--json`, `--exclude NAME`.
- Tests: stdlib unittest against fixture trees (bad python, clean python,
  JS-with-endpoints); clock injected for deadline math.

## Milestones
- [x] M1 DONE s10 (v0.1.0 tagged, pushed to pixle-codes/assistout): Python-SDK +
      raw-HTTP detection, human + JSON reports, deadline countdown, exit-code
      contract, 33 fixture tests green, README, published.
- [ ] M2: `--emit-backfill` generator producing the official thread→conversations
      export script parameterized by thread id/env var; JS/TS SDK regex pass.
- [ ] M3: per-finding rewrite hints (before/after snippets), SARIF output for
      CI annotation, pip-installable packaging if demand warrants.

## Gotchas / decisions
- Detection is regex-span based, not full AST: deliberate — zero-dep, and
  Assistants usage is overwhelmingly method-call-shaped; fixtures pin behavior.
- `.beta.vector_stores.*` intentionally NOT flagged as dead (vector stores live
  on under Responses) — flagged as re-wiring only.
- Reusable Prompts are ALSO on a deprecation timeline (2026-06-03 entry) — noted
  in knowledge base so we don't recommend stepping into the next sunset.
- Exit codes pinned by test: 0 clean, 1 findings, 2 bad path.
- Self-scan caveat (s10, verified): the scanner flags its own README examples
  and knowledge.py pattern strings — inherent to any linter reading its own
  rules; do NOT "fix" this with an exclude-list hack.
