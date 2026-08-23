"""Human and JSON report rendering."""

import json
from datetime import datetime, timezone

from . import __version__
from .knowledge import AGENTS_CLASSIC_DATE, PROMPTS_DATE, SHUTDOWN_DATE


def days_left(today=None) -> int:
    today = today or datetime.now(timezone.utc).date()
    return (SHUTDOWN_DATE - today).days


def deadline_line(label: str, shutdown_date, today=None) -> str:
    today = today or datetime.now(timezone.utc).date()
    left = (shutdown_date - today).days
    if left > 1:
        return (
            f"{label} shuts down {shutdown_date.isoformat()} "
            f"— {left} days left"
        )
    if left == 1:
        return (
            f"{label} shuts down {shutdown_date.isoformat()} "
            f"— final day"
        )
    if left == 0:
        return (
            f"{label} shutdown is TODAY ({shutdown_date.isoformat()})"
        )
    return (
        f"{label} shut down {shutdown_date.isoformat()} "
        f"({-left} days ago) — endpoints are gone, migration is mandatory"
    )


def countdown_line(today=None) -> str:
    return deadline_line("OpenAI Assistants API", SHUTDOWN_DATE, today)


def classic_agents_line(today=None) -> str:
    return deadline_line(
        "Foundry Agent Service (classic)", AGENTS_CLASSIC_DATE, today
    )


def prompts_line(today=None) -> str:
    return deadline_line("OpenAI prompt objects (v1/prompts)", PROMPTS_DATE, today)


def totals(findings):
    by_category = {}
    by_effort = {}
    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
        by_effort[f.effort] = by_effort.get(f.effort, 0) + 1
    return {
        "findings": len(findings),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "by_effort": dict(sorted(by_effort.items())),
    }


def render_json(root, findings, files_scanned, today=None):
    files = {}
    order = []
    for f in findings:
        if f.path not in files:
            files[f.path] = []
            order.append(f.path)
        files[f.path].append(
            {
                "line": f.line,
                "col": f.col,
                "category": f.category,
                "effort": f.effort,
                "match": f.match,
                "replacement": f.replacement,
                "note": f.note,
                "hint_before": f.hint_before,
                "hint_after": f.hint_after,
                "deadline": f.deadline,
            }
        )
    t = totals(findings)
    return {
        "tool": "assistout",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shutdown_date": SHUTDOWN_DATE.isoformat(),
        "agents_classic_retirement": AGENTS_CLASSIC_DATE.isoformat(),
        "prompts_shutdown_date": PROMPTS_DATE.isoformat(),
        "days_left": days_left(today),
        "scanned_root": root,
        "files_scanned": files_scanned,
        "files": [
            {"path": p, "findings": files[p]} for p in sorted(order)
        ],
        "totals": t,
    }


def render_human(findings, files_scanned, today=None):
    lines = [
        f"assistout v{__version__} — Assistants API migration scanner",
        countdown_line(today),
    ]
    if any(f.deadline == AGENTS_CLASSIC_DATE.isoformat() for f in findings):
        lines.append(classic_agents_line(today))
    if any(f.deadline == PROMPTS_DATE.isoformat() for f in findings):
        lines.append(prompts_line(today))
    lines.append("")
    if not findings:
        lines.append(
            f"No Assistants API usage found ({files_scanned} file(s) scanned)."
        )
        return "\n".join(lines)
    current = None
    prev_hint = None
    for f in findings:
        if f.path != current:
            current = f.path
            prev_hint = None
            lines.append(f"{current}")
        lines.append(
            f"  L{f.line:<4} {f.effort:<10} {f.category:<17} {f.match}"
        )
        hint = (f.hint_before, f.hint_after) if f.hint_before or f.hint_after else None
        if hint and hint != prev_hint:
            lines.append(f"        - {hint[0]}")
            lines.append(f"        + {hint[1]}")
        prev_hint = hint
    t = totals(findings)
    lines.append("")
    lines.append(
        f"Summary: {t['findings']} finding(s) across "
        f"{len({f.path for f in findings})} file(s); {files_scanned} file(s) scanned"
    )
    cats = ", ".join(f"{k} x{v}" for k, v in t["by_category"].items())
    lines.append(f"  by category: {cats}")
    eff = ", ".join(f"{k}: {v}" for k, v in t["by_effort"].items())
    lines.append(f"  by effort:   {eff}")
    lines.append("")
    lines.append(
        "Migration map: threads->conversations, runs->responses.create, "
        "assistants->inline model/instructions/tools, run steps->output items."
    )
    if any(f.deadline == PROMPTS_DATE.isoformat() for f in findings):
        lines.append(
            "Prompt objects map: pmpt_ ids / prompt={...} -> inline the "
            "prompt text as input messages (v1/prompts has no successor)."
        )
    if any(f.deadline == AGENTS_CLASSIC_DATE.isoformat() for f in findings):
        lines.append(
            "Foundry classic map: create_agent->create_version("
            "PromptAgentDefinition), threads->conversations, "
            "runs->responses.create(agent_reference)."
        )
    return "\n".join(lines)
