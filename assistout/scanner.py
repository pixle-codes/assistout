"""File walking and rule matching for Assistants API usage."""

from dataclasses import dataclass

from .knowledge import RULES, rules_for

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "site-packages",
    ".eggs",
}

MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    col: int
    category: str
    effort: str
    match: str
    replacement: str
    note: str
    hint_before: str = ""
    hint_after: str = ""


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def iter_files(root: str):
    import os

    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def scan_text(text: str, rules=None):
    rules = RULES if rules is None else rules
    claimed = []

    def overlaps(start, end):
        return any(s < end and start < e for s, e in claimed)

    hits = []
    for rule in rules:
        rx = rule.compiled()
        for m in rx.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            claimed.append((m.start(), m.end()))
            line = text.count("\n", 0, m.start()) + 1
            col = m.start() - (text.rfind("\n", 0, m.start()) + 1) + 1
            hits.append(
                {
                    "line": line,
                    "col": col,
                    "category": rule.category,
                    "effort": rule.effort,
                    "match": m.group(0)[:120],
                    "replacement": rule.replacement,
                    "note": rule.note,
                    "hint_before": rule.hint_before,
                    "hint_after": rule.hint_after,
                }
            )
    hits.sort(key=lambda h: (h["line"], h["col"]))
    return hits


def scan_path(root: str):
    findings = []
    scanned = 0
    import os

    for path in iter_files(root):
        try:
            with open(path, "rb") as fh:
                data = fh.read(MAX_BYTES + 1)
        except OSError:
            continue
        if len(data) > MAX_BYTES or is_binary(data):
            continue
        ext = os.path.splitext(path)[1].lower()
        rules = rules_for(ext)
        try:
            text = data.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        scanned += 1
        display = os.path.normpath(path)
        for hit in scan_text(text, rules):
            hit["path"] = display
            findings.append(Finding(**hit))
    return scanned, sorted(findings, key=lambda f: (f.path, f.line, f.col))
