"""CLI entry point."""

import argparse
import json
import sys

from . import __version__
from .report import render_human, render_json
from .scanner import scan_path


def build_parser():
    p = argparse.ArgumentParser(
        prog="assistout",
        description=(
            "Scan a codebase for OpenAI Assistants API usage that breaks at the "
            "2026-08-26 shutdown; maps each finding to its Responses/Conversations "
            "replacement."
        ),
    )
    p.add_argument("path", help="file or directory to scan")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--version", action="version", version=f"assistout {__version__}"
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        files_scanned, findings = scan_path(args.path)
    except OSError as exc:
        print(f"assistout: cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    if not files_scanned:
        print(f"assistout: no readable files under {args.path}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(render_json(args.path, findings, files_scanned), indent=2))
    else:
        print(render_human(findings, files_scanned))
    return 1 if findings else 0
