"""Download all available minutes PDFs referenced in meetings.json."""
import json
import time
from pathlib import Path
import requests

HERE = Path(__file__).parent
PDF_DIR = HERE.parent / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"}


def filename_for(m):
    # yyyy-mm-dd_ID-NNNN.pdf
    mm, dd, yyyy = m["date"].split("/")
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}_id-{m['meeting_id']}.pdf"


def main():
    meetings_file = HERE.parent / "meetings.json"
    meetings = json.loads(meetings_file.read_text())

    # Only meetings >= 2022-12-14 with minutes_url
    from datetime import datetime
    cutoff = datetime(2022, 12, 14)
    todo = []
    for m in meetings:
        if not m.get("minutes_url"):
            continue
        try:
            d = datetime.strptime(m["date"], "%m/%d/%Y")
        except Exception:
            continue
        if d < cutoff:
            continue
        todo.append(m)

    print(f"Downloading {len(todo)} PDFs...")
    session = requests.Session()
    session.headers.update(UA)

    ok = 0
    skipped = 0
    fail = 0
    for i, m in enumerate(todo, 1):
        fname = filename_for(m)
        path = PDF_DIR / fname
        if path.exists() and path.stat().st_size > 1000:
            skipped += 1
            continue
        try:
            r = session.get(m["minutes_url"], timeout=60)
            r.raise_for_status()
            # sanity: ensure content is PDF
            if not r.content.startswith(b"%PDF"):
                print(f"  [{i}/{len(todo)}] NOT-PDF {m['date']} id={m['meeting_id']}")
                fail += 1
                continue
            path.write_bytes(r.content)
            ok += 1
            if i % 10 == 0:
                print(f"  [{i}/{len(todo)}] saved {fname} ({len(r.content)//1024}KB)")
        except Exception as e:
            print(f"  [{i}/{len(todo)}] FAIL {m['date']}: {e}")
            fail += 1
        time.sleep(0.3)

    print(f"\nDone. ok={ok} skipped={skipped} fail={fail}")
    print(f"PDFs in {PDF_DIR}: {len(list(PDF_DIR.glob('*.pdf')))}")


if __name__ == "__main__":
    main()
