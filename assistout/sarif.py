"""SARIF 2.1.0 rendering so CI can surface findings as inline annotations."""

import hashlib
import os

from . import __version__
from .knowledge import RULES, SHUTDOWN_DATE

LEVELS = {"manual": "error", "moderate": "warning", "mechanical": "note"}
REPO_URI = "https://github.com/pixle-codes/assistout"


def level_for(effort: str) -> str:
    return LEVELS.get(effort, "warning")


def artifact_uri(path: str) -> str:
    """Repo-relative forward-slash URI when possible (GitHub requirement)."""
    try:
        rel = os.path.relpath(path, os.getcwd())
    except ValueError:
        rel = path
    return rel.replace(os.sep, "/")


def fingerprint(category: str, path: str, line: int, col: int) -> str:
    raw = f"{category}|{path}|{line}|{col}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def render_sarif(findings) -> dict:
    fired = []
    seen = set()
    for r in RULES:
        if r.category in seen:
            continue
        if any(f.category == r.category for f in findings):
            seen.add(r.category)
            fired.append(
                {
                    "id": f"assistout/{r.category}",
                    "name": r.category,
                    "shortDescription": {
                        "text": (
                            f"Assistants API usage ({r.category}) stops working "
                            "at the 2026-08-26 shutdown"
                            if r.deadline == SHUTDOWN_DATE
                            else (
                                f"Foundry classic-agents usage ({r.category}) "
                                f"stops working at the "
                                f"{r.deadline.isoformat()} retirement"
                            )
                        )
                    },
                    "fullDescription": {"text": r.note},
                    "helpUri": REPO_URI + "#what-it-detects",
                    "defaultConfiguration": {"level": level_for(r.effort)},
                    "properties": {
                        "effort": r.effort,
                        "replacement": r.replacement,
                    },
                }
            )

    results = []
    for f in findings:
        message = f"{f.match} -> use {f.replacement} [{f.effort}]"
        if f.hint_after:
            message += f" e.g. {f.hint_before} => {f.hint_after}"
        results.append(
            {
                "ruleId": f"assistout/{f.category}",
                "level": level_for(f.effort),
                "message": {"text": message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": artifact_uri(f.path)},
                            "region": {"startLine": f.line, "startColumn": f.col},
                        }
                    }
                ],
                "partialFingerprints": {
                    "assistoutLocation/v1": fingerprint(
                        f.category, f.path, f.line, f.col
                    )
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "assistout",
                        "informationUri": REPO_URI,
                        "version": __version__,
                        "rules": fired,
                    }
                },
                "results": results,
            }
        ],
    }
