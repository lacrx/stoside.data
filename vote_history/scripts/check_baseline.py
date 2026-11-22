#!/usr/bin/env python3
"""Assert that parse_votes.py still produces the committed votes.csv.

The pieces for this were already here and nothing joined them up. parse_votes.py
reads only the 90 local PDFs in vote_history/pdfs/ and makes no network call, so
it is deterministic. votes.csv and parse_log.txt are tracked in git. So a
baseline and a repeatable run both existed, and a parser edit that silently
changed the 2023 vote counts would have shown up only if somebody read the diff.

This runs the parse into a temp directory and compares. It never writes
votes.csv, so a failing check cannot destroy the baseline it is checking.

    python3 vote_history/scripts/check_baseline.py          # exit 0 or 1
    python3 vote_history/scripts/check_baseline.py -v       # per-PDF counts too
    python3 vote_history/scripts/check_baseline.py --update # re-record it

Exit codes:
    0  the parse matches the committed CSV row for row
    1  it does not, and the differences are printed
    2  the check could not run (missing PDFs, parser crash)

Line endings are normalised before comparing. The csv module writes CRLF and
the committed file has been stored both ways, which is a difference in the
bytes and not in the data.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # .../vote_history
PARSER = ROOT / "scripts" / "parse_votes.py"
BASELINE = ROOT / "votes.csv"
PDF_DIR = ROOT / "pdfs"


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def per_pdf(rows: list[dict]) -> Counter:
    return Counter(r.get("pdf_file", "?") for r in rows)


def row_key(row: dict) -> tuple:
    """What makes a row the same row across runs."""
    return (row.get("pdf_file", ""), row.get("item_number", ""),
            row.get("meeting_id", ""))


def run_parser(out_csv: Path, log_path: Path) -> int:
    proc = subprocess.run(
        [sys.executable, str(PARSER), "--out", str(out_csv), "--log", str(log_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print("ERROR: parse_votes.py failed")
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
    return proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="re-record the baseline from this parse")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="print per-PDF counts even when they match")
    args = ap.parse_args(argv)

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"ERROR: no PDFs in {PDF_DIR}. They are gitignored; "
              f"run vote_history/scripts/download_pdfs.py first.")
        return 2
    if not BASELINE.exists() and not args.update:
        print(f"ERROR: no baseline at {BASELINE}. Run with --update to record one.")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        fresh_csv = Path(tmp) / "votes.csv"
        fresh_log = Path(tmp) / "parse_log.txt"
        print(f"parsing {len(pdfs)} PDFs ...")
        if run_parser(fresh_csv, fresh_log) != 0:
            return 2

        if args.update:
            BASELINE.write_text(fresh_csv.read_text(encoding="utf-8"),
                                encoding="utf-8")
            (ROOT / "parse_log.txt").write_text(
                fresh_log.read_text(encoding="utf-8"), encoding="utf-8")
            rows = read_rows(BASELINE)
            print(f"baseline updated: {len(rows)} rows from {len(pdfs)} PDFs")
            return 0

        fresh = read_rows(fresh_csv)
        base = read_rows(BASELINE)

    print(f"baseline {len(base)} rows, parsed {len(fresh)} rows")

    fresh_counts, base_counts = per_pdf(fresh), per_pdf(base)
    moved = sorted(
        name for name in set(fresh_counts) | set(base_counts)
        if fresh_counts[name] != base_counts[name]
    )
    for name in moved:
        print(f"  COUNT {name}: baseline {base_counts[name]}, parsed {fresh_counts[name]}")
    if args.verbose and not moved:
        for name in sorted(base_counts):
            print(f"  ok {name}: {base_counts[name]}")

    fresh_by_key = {row_key(r): r for r in fresh}
    base_by_key = {row_key(r): r for r in base}
    gone = sorted(set(base_by_key) - set(fresh_by_key))
    new = sorted(set(fresh_by_key) - set(base_by_key))
    for key in gone[:20]:
        print(f"  GONE  {key[0]} item {key[1]}")
    for key in new[:20]:
        print(f"  NEW   {key[0]} item {key[1]}")

    changed = []
    for key in set(base_by_key) & set(fresh_by_key):
        b, f = base_by_key[key], fresh_by_key[key]
        fields = sorted(set(b) | set(f))
        diffs = [c for c in fields if (b.get(c) or "") != (f.get(c) or "")]
        if diffs:
            changed.append((key, diffs))
    for key, diffs in sorted(changed)[:20]:
        print(f"  CHANGED {key[0]} item {key[1]}: {', '.join(diffs)}")

    total = len(moved) + len(gone) + len(new) + len(changed)
    if total:
        print(f"\nFAIL: {len(moved)} count changes, {len(gone)} rows gone, "
              f"{len(new)} new, {len(changed)} changed")
        print("If this is a deliberate parser improvement, re-record with --update "
              "and put the row counts in the commit message.")
        return 1

    print("OK: the parse reproduces the committed baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
