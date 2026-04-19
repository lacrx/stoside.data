"""Extract text from all PDFs into data/budget_history/text/{doc_id}.txt.
Also write a JSON sidecar with page count, word count, and first-page excerpt.
"""
import json
import sys
import time
from pathlib import Path

import fitz  # pymupdf

ROOT = Path(__file__).parent.parent
PDF_DIR = ROOT / "pdfs"
TEXT_DIR = ROOT / "text"
INV = ROOT / "inventory.json"


def extract(pdf_path: Path):
    doc = fitz.open(pdf_path)
    pages_text = []
    for page in doc:
        t = page.get_text("text")
        pages_text.append(t)
    doc.close()
    full = "\n\f\n".join(pages_text)  # form-feed as page separator
    return pages_text, full


def main():
    TEXT_DIR.mkdir(exist_ok=True)
    recs = json.loads(INV.read_text())
    stats = []
    for i, r in enumerate(recs, 1):
        lp = r.get("local_path")
        if not lp:
            continue
        pdf_path = ROOT / lp
        if not pdf_path.exists():
            print(f"[{i}/{len(recs)}] missing {pdf_path}", file=sys.stderr)
            continue
        text_path = TEXT_DIR / f"{r['doc_id']}.txt"
        meta_path = TEXT_DIR / f"{r['doc_id']}.meta.json"
        if text_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            r["pages"] = meta["pages"]
            r["words"] = meta["words"]
            stats.append((r["doc_id"], meta["pages"], meta["words"]))
            continue
        t0 = time.time()
        try:
            pages, full = extract(pdf_path)
        except Exception as e:
            print(f"[{i}/{len(recs)}] FAIL {pdf_path.name}: {e}", file=sys.stderr)
            r["text_extract_error"] = str(e)
            continue
        text_path.write_text(full, encoding="utf-8")
        words = len(full.split())
        meta = {
            "doc_id": r["doc_id"],
            "title": r["title"],
            "pages": len(pages),
            "words": words,
            "chars": len(full),
            "first_page_excerpt": pages[0][:800] if pages else "",
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        r["pages"] = len(pages)
        r["words"] = words
        dt = time.time() - t0
        stats.append((r["doc_id"], len(pages), words))
        print(f"[{i}/{len(recs)}] {pdf_path.name[:70]:70} pages={len(pages):4} words={words:>7} ({dt:.1f}s)")
    INV.write_text(json.dumps(recs, indent=2))
    total_pages = sum(s[1] for s in stats)
    total_words = sum(s[2] for s in stats)
    print(f"\ndone. {len(stats)} docs  {total_pages} pages  {total_words} words")


if __name__ == "__main__":
    main()
