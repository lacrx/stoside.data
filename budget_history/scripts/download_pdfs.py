"""Download all budget PDFs listed in inventory.json.

Naming: pdfs/{doc_type}_{fiscal_year_or_title_slug}_{doc_id}.pdf
Skips already-downloaded files. Writes SHA256 + size into inventory.json.
"""
import json
import re
import hashlib
import sys
import time
from pathlib import Path
import urllib.request

BASE_DIR = Path(__file__).parent.parent
PDF_DIR = BASE_DIR / "pdfs"
INVENTORY = BASE_DIR / "inventory.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def slug(s: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s[:maxlen]


def filename_for(rec: dict) -> str:
    parts = [rec["doc_type"]]
    fy = rec.get("fiscal_year")
    if fy:
        parts.append(fy.replace(" ", ""))
    parts.append(slug(rec["title"]))
    parts.append(rec["doc_id"])
    return "_".join(parts) + ".pdf"


def download(url: str, dest: Path) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/pdf,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.ci.oceanside.ca.us/government/financial-services",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = resp.read()
    dest.write_bytes(data)
    h = hashlib.sha256(data).hexdigest()
    return len(data), h


def main():
    PDF_DIR.mkdir(exist_ok=True)
    records = json.loads(INVENTORY.read_text())
    total = len(records)
    ok = 0
    skipped = 0
    failed = []
    for i, rec in enumerate(records, 1):
        fname = filename_for(rec)
        dest = PDF_DIR / fname
        rec["local_path"] = f"pdfs/{fname}"
        if dest.exists() and dest.stat().st_size > 0:
            rec["size_bytes"] = dest.stat().st_size
            if "sha256" not in rec:
                rec["sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
            skipped += 1
            continue
        try:
            size, h = download(rec["url"], dest)
            rec["size_bytes"] = size
            rec["sha256"] = h
            ok += 1
            print(f"[{i}/{total}] {size/1024:.0f} KB  {fname}")
            time.sleep(0.3)
        except Exception as e:
            print(f"[{i}/{total}] FAIL {fname}: {e}", file=sys.stderr)
            failed.append((fname, str(e)))
            rec["download_error"] = str(e)
    INVENTORY.write_text(json.dumps(records, indent=2))
    print(f"\ndone. downloaded={ok} skipped={skipped} failed={len(failed)}")
    if failed:
        for f, e in failed:
            print(f"  FAIL {f}: {e}")


if __name__ == "__main__":
    main()
