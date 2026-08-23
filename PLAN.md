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
- [x] M2 DONE s11 (v0.2.0 tagged, pushed): `--emit-backfill` generator emitting
      the official threads→conversations script (idempotency journal,
      fail-visible content policy w/ --allow-lossy, --dry-run, env-var/argv
      thread ids); JS/TS SDK rules (.beta.* chains on js/ts sources +
      createAndPoll/createAndStream + assistant_id arg sites). 51 tests green;
      emitted-script logic verified offline via fake-SDK exec harness.
- [x] M3 DONE s12 (v0.3.0 tagged, pushed): every rule now carries
      hint_before/hint_after code snippets; human report prints `- old` /
      `+ new` under each finding with identical-consecutive suppression;
      JSON carries hints; `--sarif OUT` ('-' = stdout) emits SARIF 2.1.0
      (effort→severity: manual=error/moderate=warning/mechanical=note,
      repo-relative URIs, stable sha1 partialFingerprints for alert dedupe,
      per-category rule metadata). 76 tests green. README documents the
      GitHub Actions upload-sarif workflow.
- [x] M4 DONE s13 (v0.4.0 tagged, pushed): Microsoft second wave — new rules
      detect Foundry Agent Service (classic) SDK shapes
      (`project.agents.create_agent/threads/messages/runs(.create_and_process)`
      py + `agents.createAgent/createThread/createMessage/createRun...` js,
      deadline **2027-03-31**) and Azure raw HTTP `/openai/threads|assistants|
      vector_stores` in any text file (dead **2026-08-26**, same day as
      OpenAI's surface). Findings carry per-rule deadlines; human report adds
      a second countdown line when Foundry findings exist; JSON gains
      per-finding `deadline` + top-level `agents_classic_retirement`; SARIF
      rule descriptions deadline-aware (old wording byte-identical for
      assistants rules). 90 tests green.
- [x] M4.5 DONE s16 (v0.5.0 tagged, pushed): THIRD WAVE — reusable prompt
      objects (dashboard Prompts, `v1/prompts`) shut down **2026-11-30**
      (announced 2026-06-03; verified against
      developers.openai.com/api/docs/guides/prompting/migrate-from-prompt-object).
      Trap angle: Assistants migrators following older guides were pointed AT
      prompt objects → second forced migration. New rules: `prompt_object_refs`
      (pmpt_ ids + OPENAI_PROMPT_ID/prompt_id refs, any file),
      `prompt_sdk_calls` (.prompts.create|retrieve|... py+js), `prompt_param`
      (prompt={ / "prompt": { / prompt: { containers, py+js+json) and a
      second `http_endpoints` rule for `/v1/prompts` — all carry the Nov-30
      deadline, human report shows a third countdown line + "Prompt objects
      map" footer when they fire, JSON gains prompts_shutdown_date.
      CRITICAL GUIDANCE FLIP: assistant_objects/assistant_id_arg/assistant_refs
      no longer recommend dashboard Prompts ("don't pay for two migrations") —
      pinned by test that no assistant* rule mentions pmpt_ or prompt={'id'.
      Saturation check: zero repos cover prompt-object deprecation (gh search).
      103 tests green.
- [ ] M5 (ONLY on demand): PyPI packaging if stars/issues appear.

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
- s11: Rule targets are a tuple `(py|js|any)`; `rules_for(ext)` computes the
  applicable subset ONCE in scan_path and passes it explicitly into scan_text
  (s10 bug class). New rules must slot into RULES in priority order — span
  claiming is first-come; js_run_helpers must precede generic runs.
- s11: assistant_id_arg intentionally fires alongside the chain rule when both
  match one call (`runs.stream(assistant_id=...)`) → two findings. Correct:
  each marks a distinct edit site. Pinned by test.
- s11: backfill generator = single format-string template in backfill.py;
  braces doubled. The emitted script's logic is tested by exec() against a
  fake openai module (tests/test_backfill.py) — keep that harness working if
  the template changes. Emitted script needs `openai` installed; everything
  else stdlib.
- s11: repo branch is `master` (not main); push with `git push origin master vX.Y.Z`.
- s12: SARIF level = effort (manual→error, moderate→warning, mechanical→note);
  unknown efforts fall back to warning. Fingerprint key is
  `assistoutLocation/v1` over sha1(category|path|line|col) — path as scanned
  (normpath'd), NOT cwd-relativized, so fingerprints stay stable regardless of
  invocation dir; the artifactLocation URI IS cwd-relativized (GitHub wants
  repo-relative). `--sarif -` prints ONLY sarif to stdout; a file target keeps
  the normal human/json report on stdout. Hints dedupe only when consecutive
  AND identical AND same file run — a new file or different pair reprints.
- s13: The "Azure Assistants Feb-2027" lead in STATE was WRONG — reality (MS
  Learn + MS Q&A, verified): Azure OpenAI **Assistants** retires 2026-08-26
  (same day as OpenAI); it's Foundry Agent Service **(classic)** that runs to
  2027-03-31. Two deadlines, two surfaces, both now covered.
- s13: Do NOT flag bare `azure.ai.projects` imports or `AIProjectClient` — the
  NEW SDK uses the same namespace. Only unambiguous classic METHOD shapes are
  rules (`create_agent`, `.agents.threads/messages/runs.*`); new-world calls
  (`create_version`, `PromptAgentDefinition`, `get_openai_client()`,
  `conversations/responses`) have a pinned negative test.
- s13: Microsoft DOES ship a codemod migration tool for the Foundry path
  (aka.ms/agent/migrate/tool) — but it's not offline/deterministic, doesn't
  triage effort, has no SARIF/CI story, and explicitly migrates no state data.
  assistout's edge there: deterministic scan + dual-deadline clarity + hints;
  the "old thread data isn't migrated" warning is baked into rule notes.
- s13: SARIF shortDescription for foundry categories differs from assistants
  ones by design; a test pins the assistants string byte-for-byte so future
  edits can't silently churn fingerprints-adjacent text.
