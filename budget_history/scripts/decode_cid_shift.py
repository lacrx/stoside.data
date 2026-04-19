"""Oceanside ACFR/Measure X PDFs sometimes use a custom font encoding where
glyph indexes are off-by-29 from Unicode code points: text like 'CITY' extracts
as '&,7<' because pymupdf surfaces the raw glyph indices.

There are two source ranges of the shift:

  * Range A — Printable-ASCII source (titles/headers). 'CITY' extracts as
    '&,7<'. Shift 33..97 by +29 to recover 'A'..'z'.
  * Range B — Control-char source (table bodies, common in FY 2010–2019).
    Digits extract as \\x13..\\x1c, space as \\x03, comma as \\x0f, '$' as
    \\x07. Shift 0..8, 11, 14..31 by +29 to recover printable ASCII 29..60.

Range B is *always* safe to apply: pymupdf never emits control chars like
\\x03, \\x07, \\x13 in clean text, so anywhere they appear they're garbled.
Range A is only safe when the page has essentially no legitimate lowercase
letters (otherwise we'd corrupt real body prose).
"""
import json
import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).parent.parent
TEXT_DIR = ROOT / "text"
PDF_DIR = ROOT / "pdfs"
INV = ROOT / "inventory.json"

GARBLED_MARKERS = ["&,7<", "),1$1&,$/", "&,7<2)", "7$%/(2)"]

# Signature phrases that only appear in Range-A garbled Oceanside AFR text.
# Used to force Range-A shift on table-continuation pages where the density
# test fails (mixed content: Range-A labels + Range-B numbers + a little
# real lowercase). These are deliberately narrow strings that a clean page
# has zero chance of containing.
def _encode_garbled(s: str) -> str:
    """Reverse-shift a clean English string to its Range-A/Range-B encoded
    form — every char has -29 subtracted from its ordinal. Used to build
    signature patterns that match the *raw* PDF text (where space becomes
    \\x03, '-' becomes \\x10, letters become Range-A garbled chars)."""
    return "".join(chr(ord(c) - 29) if ord(c) >= 29 else c for c in s)


# Signature phrases, in raw-extraction form, that only appear in Range-A
# garbled Oceanside AFR/ACFR text. We build them from their clean English
# equivalents so they're readable in source but match the raw byte sequence
# including Range-B encoded spaces (\x03) and hyphens (\x10).
_SIG_PHRASES = [
    "CITY OF OCEANSIDE",
    "Primary Government",
    "Net (Expenses",
    "STATEMENT OF ACTIVITIES",
    "STATEMENT OF NET",
    "General Revenues",
    "Total General Revenues",
    "Change in Net Position",
    "Total Governmental Activities",
]
GARBLED_SIGNATURE_RE = re.compile("|".join(re.escape(_encode_garbled(s))
                                           for s in _SIG_PHRASES))

# A run that's a candidate for shifting:
#   - consists of chars in 32..96 (printable ASCII minus lowercase)
#   - ≥ 3 chars long
RUN_RE = re.compile(r"[\x20-\x60]{3,}")


def _is_garbled_run(run: str) -> bool:
    if len(run) < 3:
        return False
    if re.search(r"[a-z]", run):
        return False
    # The run is garbled iff shifting it by +29 would produce a high
    # proportion of lowercase letters. Clean uppercase text (e.g., headings
    # like "ASSETS, LIABILITIES") won't yield lowercase.
    body = [c for c in run if not c.isspace()]
    if len(body) < 3:
        return False
    would_lower = sum(1 for c in body if 68 <= ord(c) <= 93)
    return would_lower / len(body) > 0.60


def shift_run(run: str, delta: int = 29) -> str:
    """Apply Range-A shift: printable ASCII 33..97 → 62..126. Preserves
    whitespace and anything outside that range."""
    out = []
    for ch in run:
        o = ord(ch)
        if 33 <= o <= 97:
            out.append(chr(o + delta))
        else:
            out.append(ch)
    return "".join(out)


def shift_range_b(text: str, delta: int = 29) -> str:
    """Always-on shift for control-char-encoded glyphs (Range B). Shifts
    0..8, 11, 14..31 to 29..60 (printable: $, (, ), *, +, ',', '-', '.',
    '/', and digits 0..9). Leaves \\t, \\n, \\f, \\r and regular text alone.
    These control chars never appear in clean extracted text, so the shift
    is safe without any detection heuristic.
    """
    out = []
    for ch in text:
        o = ord(ch)
        if (0 <= o <= 8) or o == 11 or (14 <= o <= 31):
            out.append(chr(o + delta))
        else:
            out.append(ch)
    return "".join(out)


def decode_text(text: str) -> str:
    """Shift only garbled runs within the text."""
    def repl(m):
        run = m.group(0)
        return shift_run(run) if _is_garbled_run(run) else run
    return RUN_RE.sub(repl, text)


def page_is_garbled(text: str) -> bool:
    """A page is a candidate for Range-A shift if:
      (a) it contains a known Range-A signature phrase (see
          GARBLED_SIGNATURE_RE) — these appear nowhere in clean text,
          so they're an unambiguous positive signal; OR
      (b) it contains essentially no lowercase letters AND high density of
          68..93 source chars (lowercase-target) AND high density of
          36..47-non-digit / 58..61 source chars (uppercase-target).

      The uppercase-target signal is critical: native ALL-CAPS text like
      'THIS PAGE INTENTIONALLY LEFT BLANK' has many 68..93 chars (I, T, Y,
      O, N, P, L, etc.) but zero 36..47-non-digit chars. Range-A garbled
      text has both ranges populated because the source has mixed case.
    """
    if GARBLED_SIGNATURE_RE.search(text):
        return True
    body = [c for c in text if not c.isspace()]
    if len(body) < 10:
        return False
    lowers = sum(1 for c in body if c.islower())
    if lowers > 3:
        return False
    pre_lower = sum(1 for c in body if 68 <= ord(c) <= 93)
    # upper_source: chars that would shift to uppercase A-Z. Excludes digits
    # (48-57) which are legitimate numerics. Chars in 36-47 non-digit are:
    # $ % & ' ( ) * + , - . /. Range 58-61 is : ; < =. Clean text has <=2
    # such chars (occasional comma in a title); garbled has many.
    upper_source = sum(1 for c in body if
                       (36 <= ord(c) <= 47 and not c.isdigit())
                       or 58 <= ord(c) <= 61)
    return (pre_lower > 10
            and pre_lower / len(body) > 0.25
            and upper_source > 3)


def decode_pdf(pdf_path: Path) -> tuple[str, int]:
    """Two-phase decode per page:
      1. Range-A shift on the whole page, *only* when the page is a
         fully-garbled candidate (page_is_garbled — no real lowercase,
         high density of 68..93 source chars). Per-run decoding is unsafe:
         clean uppercase words like 'CITY' match the same shape as
         Range-A garbled 'city' would, and per-run detection can't
         distinguish them.
      2. Range-B shift on remaining control chars (always on) — produces
         digits, $, comma, etc. from the \\x00..\\x1f range. Safe to apply
         unconditionally because clean text never contains these chars.

    Consequence for mixed-content pages (FY 2010–2019 AFRs where pymupdf
    interleaves a Range-A garbled title with clean body text): the title
    remains garbled but the body — and crucially the Range-B-encoded
    numeric values — comes out clean. Parsers should anchor on body
    markers (e.g., 'Capital assets, not being depreciated') not on titles.
    """
    doc = fitz.open(pdf_path)
    pages_out = []
    fixed = 0
    for page in doc:
        text = page.get_text("text")
        # Phase 1: Range-A — whole-page, only if the page is fully garbled
        if page_is_garbled(text):
            new = shift_run(text)
            fixed += 1
        else:
            new = text
        # Phase 2: Range-B — always safe on remaining control chars
        new = shift_range_b(new)
        pages_out.append(new)
    doc.close()
    return "\n\f\n".join(pages_out), fixed


def main():
    inv = json.loads(INV.read_text())
    candidates = [r for r in inv if r["doc_type"] in ("acfr", "measure_x_report")]
    fixed_total = 0
    for r in candidates:
        doc_id = r["doc_id"]
        text_path = TEXT_DIR / f"{doc_id}.txt"
        if not text_path.exists():
            continue
        # Decode PDF if any page is garbled (not just the cover).
        pdf_path = ROOT / r["local_path"]
        print(f"[{r['fiscal_year']} {r['doc_type']}] decoding {pdf_path.name}", file=sys.stderr)
        new_text, fixed = decode_pdf(pdf_path)
        # If the PDF yields near-empty text (image-only scan), preserve the
        # existing text file — it likely came from a prior OCR run
        # (scripts/ocr_scanned_afrs.py) which is the only source of text
        # for these scanned AFRs.
        existing = text_path.read_text(encoding="utf-8", errors="replace")
        if len(new_text.strip()) < 500 and len(existing.strip()) > 1000:
            print(f"  PDF extract is near-empty; preserving OCR text "
                  f"({len(existing)} chars)", file=sys.stderr)
            continue
        text_path.write_text(new_text, encoding="utf-8")
        meta_path = TEXT_DIR / f"{doc_id}.meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            meta["words"] = len(new_text.split())
            meta["chars"] = len(new_text)
            meta["first_page_excerpt"] = new_text.split("\x0c")[0][:800]
            meta["cid_shift_pages_fixed"] = fixed
            meta_path.write_text(json.dumps(meta, indent=2))
        fixed_total += fixed
        print(f"  fixed {fixed} pages", file=sys.stderr)
    print(f"\ntotal pages re-decoded: {fixed_total}", file=sys.stderr)


if __name__ == "__main__":
    main()
