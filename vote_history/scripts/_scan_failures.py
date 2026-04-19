"""Scan all PDFs for failure-like patterns that the main parser may have missed."""
import pdfplumber
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "pdfs"

patterns = {
    "dies_for_lack": r"(?i)motion\s+dies?\s+for\s+lack\s+of\s+(?:a\s+)?second",
    "failed_count":  r"(?im)^\s*(?:Failed|Denied|Defeated|Rejected|Withdrawn|Tabled|Continued)\s*:\s*\d+\s*[-\u2013]\s*\d+",
    "result_failed": r"(?i)RESULT\s*:\s*(?:FAILED|DENIED|DEFEATED|REJECTED|WITHDRAWN|TABLED|CONTINUED)",
    "motion_failed": r"(?i)\b(?:the\s+)?motion\s+(?:failed|fails|failed\s+to\s+carry|did\s+not\s+pass|was\s+not\s+approved)",
}

def main():
    hits = {k: [] for k in patterns}
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    for p in pdfs:
        with pdfplumber.open(p) as pdf:
            text = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
        for k, pat in patterns.items():
            for m in re.finditer(pat, text):
                s = max(0, m.start() - 200)
                e = min(len(text), m.end() + 300)
                ctx = re.sub(r"\s+", " ", text[s:e])
                hits[k].append((p.name, ctx[:400]))
    for k, lst in hits.items():
        print(f"=== {k}: {len(lst)} hits ===")
        for fn, ctx in lst:
            print(f"  {fn}")
            print(f"    ...{ctx}...")
        print()

if __name__ == "__main__":
    main()
