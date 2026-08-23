"""Human and JSON report rendering."""

import json
from datetime import datetime, timezone

from . import __version__
from .knowledge import SHUTDOWN_DATE


def days_left(today=None) -> int:
    today = today or datetime.now(timezone.utc).date()
    return (SHUTDOWN_DATE - today).days


def countdown_line(today=None) -> str:
    left = days_left(today)
    if left > 1:
        return (
            f"OpenAI Assistants API shuts down {SHUTDOWN_DATE.isoformat()} "
            f"— {left} days left"
        )
    if left == 1:
        return (
            f"OpenAI Assistants API shuts down {SHUTDOWN_DATE.isoformat()} "
            f"— final day"
        )
    if left == 0:
        return (
            f"OpenAI Assistants API shutdown is TODAY ({SHUTDOWN_DATE.isoformat()})"
        )
    return (
        f"OpenAI Assistants API shut down {SHUTDOWN_DATE.isoformat()} "
        f"({-left} days ago) — endpoints are gone, migration is mandatory"
    )


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
            }
        )
    t = totals(findings)
    return {
        "tool": "assistout",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shutdown_date": SHUTDOWN_DATE.isoformat(),
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
        "",
    ]
    if not findings:
        lines.append(
            f"No Assistants API usage found ({files_scanned} file(s) scanned)."
        )
        return "\n".join(lines)
    current = None
    for f in findings:
        if f.path != current:
            current = f.path
            lines.append(f"{current}")
        lines.append(
            f"  L{f.line:<4} {f.effort:<10} {f.category:<17} {f.match}"
        )
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
        "assistants->dashboard prompts, run steps->output items."
    )
    return "\n".join(lines)
