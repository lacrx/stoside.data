"""OCR the five FY 2001-2007 scanned AFRs so their text becomes parseable.

Prerequisites
-------------
Tesseract OCR must be installed locally. This script uses pymupdf's built-in
`page.get_textpage_ocr()` which shells out to the system Tesseract binary.

On Windows, the recommended install is:

    winget install UB-Mannheim.TesseractOCR

…or download the installer from
https://github.com/UB-Mannheim/tesseract/wiki and add the install directory to
PATH. Verify with ``tesseract --version``. If tesseract is on PATH, pymupdf's
OCR will pick it up automatically via the TESSDATA_PREFIX that the installer
sets up.

What this script does
---------------------
For each scanned AFR PDF (enumerated below), it:
  1. Runs OCR page-by-page at 200 DPI (good balance of accuracy vs. speed).
  2. Writes the output to ``text/{doc_id}.txt`` (overwriting any empty
     extract). Page separator is `\\f` to match `extract_text.py`.
  3. Updates the ``words`` count in the matching ``text/{doc_id}.meta.json``.

After running, re-run the CID-shift decoder and the decoder-inputs parser;
they'll pick up the newly-populated text files. OCR accuracy on the audited
schedules is usually good enough to extract `Capital assets, not being
depreciated` and Total rows — expect some errors on densely-packed numeric
columns which may need manual cross-check against the PDF.

Usage:
    python scripts/ocr_scanned_afrs.py
"""
import json
import sys
import time
from pathlib import Path

import fitz  # pymupdf

ROOT = Path(__file__).parent.parent
PDF_DIR = ROOT / "pdfs"
TEXT_DIR = ROOT / "text"

# Doc IDs of the FY 2001-2007 AFR Financial Sections known to be image-only
# (pymupdf extracts 0 words from them). Update this list if more scanned
# docs are discovered. IDs come from inventory.json.
SCANNED_DOCS = [
    ("8310", "FY2001 AFR"),
    ("8318", "FY2003 AFR Financial"),
    ("8250", "FY2004 AFR Financial"),
    ("8262", "FY2006 AFR Financial"),
    ("8268", "FY2007 AFR Financial"),
]

DPI = 200


def ocr_pdf(pdf_path: Path) -> tuple[str, int]:
    """Run Tesseract OCR on every page of `pdf_path` and return combined text
    separated by form-feed. Returns (text, n_pages)."""
    doc = fitz.open(pdf_path)
    pages_text = []
    for i, page in enumerate(doc):
        try:
            tp = page.get_textpage_ocr(language="eng", dpi=DPI, full=True)
            pages_text.append(page.get_text(textpage=tp))
        except Exception as e:
            print(f"    page {i+1} OCR failed: {e}", file=sys.stderr)
            pages_text.append("")
    doc.close()
    return "\n\f\n".join(pages_text), len(pages_text)


def main():
    TEXT_DIR.mkdir(exist_ok=True)
    for doc_id, label in SCANNED_DOCS:
        # Find the PDF by doc_id suffix
        matches = list(PDF_DIR.glob(f"*_{doc_id}.pdf"))
        if not matches:
            print(f"[skip {doc_id} {label}] no PDF found", file=sys.stderr)
            continue
        pdf_path = matches[0]
        text_path = TEXT_DIR / f"{doc_id}.txt"
        meta_path = TEXT_DIR / f"{doc_id}.meta.json"
        t0 = time.time()
        print(f"[OCR {doc_id} {label}] {pdf_path.name}", file=sys.stderr)
        try:
            full, n_pages = ocr_pdf(pdf_path)
        except RuntimeError as e:
            if "Tesseract" in str(e):
                print(f"\nERROR: Tesseract is not installed or not on PATH.",
                      file=sys.stderr)
                print("  Install via: winget install UB-Mannheim.TesseractOCR",
                      file=sys.stderr)
                print("  Or download from https://github.com/UB-Mannheim/tesseract/wiki",
                      file=sys.stderr)
                sys.exit(1)
            raise
        text_path.write_text(full, encoding="utf-8")
        words = len(full.split())
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        meta.update({
            "doc_id": doc_id,
            "pages": n_pages,
            "words": words,
            "chars": len(full),
            "first_page_excerpt": full.split("\f")[0][:800] if full else "",
            "ocr_applied": True,
            "ocr_dpi": DPI,
        })
        meta_path.write_text(json.dumps(meta, indent=2))
        dt = time.time() - t0
        print(f"  wrote {n_pages} pages, {words} words ({dt:.0f}s)",
              file=sys.stderr)


if __name__ == "__main__":
    main()
