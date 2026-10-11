"""Command-line interface for ghostapi."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .checker import check_file

FORMATS = ("text", "json")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ghostapi",
        description=(
            "Scan Python files for hallucinated or deprecated API usage. "
            "Verifies every call through an imported name with a real import; "
            "nothing is ever executed."
        ),
    )
    p.add_argument("files", nargs="*", help="Python files to scan")
    p.add_argument(
        "-f", "--format", choices=FORMATS, default="text",
        help="output format (default: text)",
    )
    p.add_argument(
        "-q", "--quiet", action="store_true",
        help="only print findings, no summary line",
    )
    p.add_argument("--version", action="version", version=f"ghostapi {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.files:
        print("ghostapi: no input files", file=sys.stderr)
        return 2

    all_findings = []
    for path in args.files:
        try:
            result = check_file(path)
        except FileNotFoundError:
            print(f"ghostapi: file not found: {path}", file=sys.stderr)
            return 2
        except SyntaxError as e:
            print(f"ghostapi: syntax error in {path}: {e}", file=sys.stderr)
            return 2
        except OSError as e:
            print(f"ghostapi: cannot read {path}: {e}", file=sys.stderr)
            return 2
        all_findings.extend(result.findings)

    if args.format == "json":
        print(json.dumps([f.as_dict() for f in all_findings], indent=2))
    else:
        for f in all_findings:
            print(f.one_line())

    if not args.quiet:
        n = len(all_findings)
        if n == 0:
            print("ghostapi: clean -- no hallucinated or deprecated API usage found")
        else:
            print(
                f"ghostapi: {n} finding{'s' if n != 1 else ''} "
                f"in {len(args.files)} file{'s' if len(args.files) != 1 else ''}"
            )
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
