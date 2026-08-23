"""CLI entry point."""

import argparse
import json
import os
import sys

from . import __version__
from .backfill import generate_script
from .report import render_human, render_json
from .sarif import render_sarif
from .scanner import scan_path


def build_parser():
    p = argparse.ArgumentParser(
        prog="assistout",
        description=(
            "Scan a codebase for OpenAI Assistants API usage that breaks at the "
            "2026-08-26 shutdown, plus Microsoft Foundry Agent Service (classic) "
            "shapes retiring 2027-03-31 and Azure /openai/threads|assistants "
            "HTTP calls; maps each finding to its Responses/Conversations "
            "replacement."
        ),
    )
    p.add_argument(
        "path", nargs="?", help="file or directory to scan", default=None
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--sarif",
        metavar="OUT",
        help=(
            "write findings as SARIF 2.1.0 to OUT ('-' for stdout) for "
            "GitHub code-scanning annotations; exit codes unchanged"
        ),
    )
    p.add_argument(
        "--emit-backfill",
        metavar="OUT",
        help=(
            "write the official Threads->Conversations backfill script to OUT "
            "('-' for stdout) and exit; run it before 2026-08-26"
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="with --emit-backfill: overwrite an existing file",
    )
    p.add_argument(
        "--version", action="version", version=f"assistout {__version__}"
    )
    return p


def emit_backfill(args) -> int:
    src = generate_script()
    out = args.emit_backfill
    if out == "-":
        sys.stdout.write(src)
        return 0
    if os.path.exists(out) and not args.force:
        print(
            f"assistout: {out} exists; use --force to overwrite",
            file=sys.stderr,
        )
        return 2
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(src)
    except OSError as exc:
        print(f"assistout: cannot write {out}: {exc}", file=sys.stderr)
        return 2
    print(
        f"wrote {out} ({len(src.splitlines())} lines). "
        f"Run it with your thread IDs BEFORE 2026-08-26; "
        f"see --help inside the script."
    )
    return 0


def write_sarif(out: str, findings) -> int:
    payload = json.dumps(render_sarif(findings), indent=2)
    if out == "-":
        print(payload)
        return 0
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    except OSError as exc:
        print(f"assistout: cannot write {out}: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.emit_backfill:
        return emit_backfill(args)
    if not args.path:
        build_parser().error("PATH is required (or use --emit-backfill)")
    try:
        files_scanned, findings = scan_path(args.path)
    except OSError as exc:
        print(f"assistout: cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    if not files_scanned:
        print(f"assistout: no readable files under {args.path}", file=sys.stderr)
        return 2
    sarif_to_stdout = args.sarif == "-"
    if args.sarif and not sarif_to_stdout:
        rc = write_sarif(args.sarif, findings)
        if rc:
            return rc
    if sarif_to_stdout:
        write_sarif("-", findings)
    elif args.json:
        print(json.dumps(render_json(args.path, findings, files_scanned), indent=2))
    else:
        print(render_human(findings, files_scanned))
    return 1 if findings else 0
