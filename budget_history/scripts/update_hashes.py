"""Refresh local_path / size / sha256 in inventory.json based on actual files on disk."""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PDF_DIR = ROOT / "pdfs"
INV = ROOT / "inventory.json"


def main():
    recs = json.loads(INV.read_text())
    present = {p.name for p in PDF_DIR.iterdir() if p.suffix == ".pdf"}
    updated = 0
    missing = []
    for r in recs:
        # Strip trailing CR if any leaked in; canonicalize local_path
        lp = r.get("local_path", "").rstrip("\r ").strip()
        if not lp:
            continue
        fname = Path(lp).name
        dest = PDF_DIR / fname
        if not dest.exists():
            missing.append(fname)
            continue
        data = dest.read_bytes()
        r["local_path"] = f"pdfs/{fname}"
        r["size_bytes"] = len(data)
        r["sha256"] = hashlib.sha256(data).hexdigest()
        r.pop("download_error", None)
        updated += 1
    INV.write_text(json.dumps(recs, indent=2))
    print(f"updated={updated} missing={len(missing)}")
    for m in missing[:10]:
        print(f"  missing: {m}")


if __name__ == "__main__":
    main()
