"""
Derive per-councilmember and per-meeting markdown views from votes.csv.
Source of truth is votes.csv; these views are regenerable.
"""
import csv
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
CSV_FILE = ROOT / "votes.csv"
MEMBER_DIR = ROOT / "by_member"
MEETING_DIR = ROOT / "by_meeting"
MEMBER_DIR.mkdir(exist_ok=True)
MEETING_DIR.mkdir(exist_ok=True)

MEMBERS = ["SANCHEZ", "KEIM", "JOYCE", "ROBINSON", "WEISS", "FIGUEROA", "RODRIGUEZ"]


def load():
    with open(CSV_FILE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_member_file(name, rows):
    """Every vote cast by this member."""
    # Only rows where they voted (not NotOnCouncil / Absent with no position recorded).
    # Include Absent rows too so you can see attendance.
    tally = defaultdict(int)
    for r in rows:
        tally[r[name]] += 1

    out = [f"# Votes by {name.title()}", ""]
    out.append(f"**Total votes cast** (Yes/No/Abstain): "
               f"{tally['Yes'] + tally['No'] + tally['Abstain']}")
    out.append(f"- Yes: {tally['Yes']}")
    out.append(f"- No: {tally['No']}")
    out.append(f"- Abstain: {tally['Abstain']}")
    out.append(f"- Absent: {tally['Absent']}")
    out.append(f"- Unknown: {tally['Unknown']}")
    out.append(f"- Not on council (before/after term): {tally['NotOnCouncil']}")
    out.append("")
    out.append("## Dissents and abstentions")
    out.append("")
    out.append("Votes where this member broke from a majority or abstained:")
    out.append("")
    out.append("| Date | Item | Position | Outcome | Title |")
    out.append("|------|------|----------|---------|-------|")

    interesting = []
    for r in rows:
        pos = r[name]
        if pos in ("No", "Abstain"):
            interesting.append(r)
    interesting.sort(key=lambda r: r["meeting_date"])
    for r in interesting:
        title = (r["item_title"] or "")[:80].replace("|", "\\|")
        out.append(
            f"| {r['meeting_date']} | #{r['item_number']} | **{r[name]}** | "
            f"{r['outcome']} {r['vote_count_for']}-{r['vote_count_against']} | {title} |"
        )

    out.append("")
    out.append("## All votes")
    out.append("")
    out.append("| Date | Item | Position | Outcome | Mover | Second | Title |")
    out.append("|------|------|----------|---------|-------|--------|-------|")
    for r in sorted(rows, key=lambda r: (r["meeting_date"], int(r["item_number"] or 0))):
        pos = r[name]
        if pos == "NotOnCouncil":
            continue
        title = (r["item_title"] or "")[:70].replace("|", "\\|")
        out.append(
            f"| {r['meeting_date']} | #{r['item_number']} | {pos} | "
            f"{r['outcome']} {r['vote_count_for']}-{r['vote_count_against']} | "
            f"{r['mover']} | {r['seconder']} | {title} |"
        )

    path = MEMBER_DIR / f"{name.lower()}.md"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def write_meeting_file(date, mid, rows):
    rows = sorted(rows, key=lambda r: int(r["item_number"] or 0))
    pdf = rows[0]["pdf_file"]
    out = [f"# Council Meeting {date}", ""]
    out.append(f"Meeting ID: {mid}")
    out.append(f"PDF: [{pdf}](../pdfs/{pdf})")
    out.append(f"Votes recorded: {len(rows)}")
    out.append("")
    out.append("| # | Outcome | Mover | Second | " +
               " | ".join(MEMBERS) + " | Title |")
    out.append("|---|---------|-------|--------|" +
               "|".join(["---"] * len(MEMBERS)) + "|-------|")
    for r in rows:
        title = (r["item_title"] or "")[:80].replace("|", "\\|")
        cells = [
            r["item_number"],
            f"{r['outcome']} {r['vote_count_for']}-{r['vote_count_against']}",
            r["mover"], r["seconder"],
        ]
        for m in MEMBERS:
            v = r[m]
            short = {"Yes": "Y", "No": "**N**", "Abstain": "Abs",
                     "Absent": "—", "NotOnCouncil": ".", "Unknown": "?"}.get(v, v)
            cells.append(short)
        cells.append(title)
        out.append("| " + " | ".join(cells) + " |")

    out.append("")
    # Notes
    notes = [r for r in rows if r["notes"]]
    if notes:
        out.append("## Notes")
        out.append("")
        for r in notes:
            out.append(f"- Item #{r['item_number']}: {r['notes']}")

    path = MEETING_DIR / f"{date}.md"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def main():
    rows = load()
    print(f"Loaded {len(rows)} votes")

    # Per-member files
    for m in MEMBERS:
        p = write_member_file(m, rows)
        print(f"  wrote {p.relative_to(ROOT)}")

    # Per-meeting files
    by_meeting = defaultdict(list)
    for r in rows:
        by_meeting[(r["meeting_date"], r["meeting_id"])].append(r)
    for (date, mid), meeting_rows in sorted(by_meeting.items()):
        write_meeting_file(date, mid, meeting_rows)
    print(f"  wrote {len(by_meeting)} meeting files")

    # Top-level index
    index = ["# Oceanside City Council Vote History", ""]
    index.append("Source of truth: [votes.csv](votes.csv) "
                 "(1 row = 1 vote, individual member positions as columns).")
    index.append("")
    index.append("## By councilmember")
    index.append("")
    for m in MEMBERS:
        index.append(f"- [{m.title()}](by_member/{m.lower()}.md)")
    index.append("")
    index.append("## By meeting")
    index.append("")
    index.append(f"{len(by_meeting)} meetings — see [by_meeting/](by_meeting/).")
    index.append("")
    index.append("## Source PDFs")
    index.append("")
    pdfs = sorted((ROOT / "pdfs").glob("*.pdf"))
    index.append(f"{len(pdfs)} minutes PDFs — see [pdfs/](pdfs/).")
    index.append("")
    index.append("## Meeting catalog")
    index.append("")
    index.append("[meetings.json](meetings.json) — full Legistar enumeration "
                 "of City Council meetings Dec 2022 – Apr 2026, with agenda / "
                 "minutes / packet URLs.")
    index.append("")
    index.append("## Parsing notes")
    index.append("")
    index.append("See [parse_log.txt](parse_log.txt) for per-PDF counts and warnings.")
    (ROOT / "index.md").write_text("\n".join(index), encoding="utf-8")
    print(f"  wrote index.md")


if __name__ == "__main__":
    main()
