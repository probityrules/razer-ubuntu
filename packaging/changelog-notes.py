#!/usr/bin/env python3
"""Extract one version section from CHANGELOG.md for GitHub Release notes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract(changelog: Path, version: str) -> str:
    text = changelog.read_text(encoding="utf-8")
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, text, flags=re.M | re.S)
    if not match:
        return ""
    return match.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Version to extract, e.g. 0.18.0")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to CHANGELOG.md",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write to this file instead of stdout",
    )
    args = parser.parse_args()

    if not args.changelog.is_file():
        print(f"Missing changelog: {args.changelog}", file=sys.stderr)
        return 1

    body = extract(args.changelog, args.version)
    if args.output is not None:
        args.output.write_text(body + ("\n" if body else ""), encoding="utf-8")
    else:
        sys.stdout.write(body + ("\n" if body else ""))

    if not body:
        print(f"::warning::No CHANGELOG.md section for {args.version}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
