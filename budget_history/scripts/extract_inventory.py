"""Parse Oceanside finance HTML pages and extract budget document inventory."""
import re
import json
import html
import sys
from pathlib import Path

BASE = "https://www.ci.oceanside.ca.us"
SCRIPTS_DIR = Path(__file__).parent
OUT_DIR = SCRIPTS_DIR.parent

LINK_RE = re.compile(
    r'aria-label=\'Click to download ([^\']+) PDF file\'[^>]*href="(/home/showpublisheddocument/(\d+)/(\d+))"',
    re.IGNORECASE,
)

# Source page -> logical category
SOURCES = {
    "operating-budget.html": "operating_budget",
    "cafr.html": "cafr",
    "budget-in-brief.html": "budget_in_brief",
    "financial-services.html": "financial_services_index",
    "quarterly.html": "quarterly",
    "single-audit.html": "single_audit",
    "measure-x.html": "measure_x",
    "component-unit.html": "component_unit",
    "sales-tax.html": "sales_tax",
    "cip.html": "operating_budget",  # CIP lives under operating budget category
}
# Glob-based subfolder sources
SOURCE_GLOBS = {
    "q_*.html": "quarterly",
    "cu_*.html": "component_unit",
    "st_*.html": "sales_tax",
}


def classify(title: str, source_category: str) -> str:
    t = title.lower()
    if source_category == "cafr":
        if "single audit" in t:
            return "single_audit"
        if "popular" in t or "pafr" in t:
            return "pafr"
        return "acfr"
    if source_category == "budget_in_brief":
        return "budget_in_brief"
    if source_category == "operating_budget":
        if "mid" in t and "year" in t:
            return "midyear_review"
        if "proposed" in t:
            return "proposed_budget"
        if "capital" in t and "improvement" in t:
            return "cip"
        if "biennial" in t:
            return "biennial_budget"
        if "adopted" in t or "operating budget" in t:
            return "adopted_budget"
        return "budget_supplement"
    if source_category == "quarterly":
        # Derive quarter number
        m = re.search(r"(\d)(?:st|nd|rd|th)\s*quarter", t)
        if m:
            return f"quarterly_q{m.group(1)}"
        return "quarterly_report"
    if source_category == "single_audit":
        return "single_audit"
    if source_category == "measure_x":
        return "measure_x_report"
    if source_category == "component_unit":
        return "component_unit"
    if source_category == "sales_tax":
        return "sales_tax_newsletter"
    return "other"


FY_RE = re.compile(r"FY\s*(\d{4})[-/](\d{2,4})", re.IGNORECASE)
BIENNIAL_RE = re.compile(r"(\d{4})-(\d{4})\b")
SINGLE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def extract_fiscal_year(title: str) -> str | None:
    m = FY_RE.search(title)
    if m:
        start = m.group(1)
        end = m.group(2)
        if len(end) == 2:
            end = start[:2] + end
        return f"FY{start}-{end}"
    m = BIENNIAL_RE.search(title)
    if m:
        return f"FY{m.group(1)}-{m.group(2)}"
    m = SINGLE_YEAR_RE.search(title)
    if m:
        return f"FY{m.group(1)}"
    return None


def _iter_source_files():
    for fname, category in SOURCES.items():
        path = SCRIPTS_DIR / fname
        if path.exists():
            yield path, category
    for pattern, category in SOURCE_GLOBS.items():
        for path in sorted(SCRIPTS_DIR.glob(pattern)):
            yield path, category


def main():
    records = []
    seen = set()
    for path, category in _iter_source_files():
        fname = path.name
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in LINK_RE.finditer(text):
            title_raw = html.unescape(m.group(1))
            rel_url = m.group(2)
            doc_id = m.group(3)
            ts = m.group(4)
            if doc_id in seen:
                continue
            seen.add(doc_id)
            rec = {
                "doc_id": doc_id,
                "title": title_raw,
                "url": BASE + rel_url,
                "timestamp": ts,
                "source_page": fname,
                "source_category": category,
                "doc_type": classify(title_raw, category),
                "fiscal_year": extract_fiscal_year(title_raw),
            }
            records.append(rec)
    records.sort(key=lambda r: (r["source_category"], r["fiscal_year"] or "", r["title"]))
    out = OUT_DIR / "inventory_raw.json"
    out.write_text(json.dumps(records, indent=2))
    print(f"wrote {len(records)} records -> {out}")

    # Filter since FY2001 (earliest material on the city portal).
    # Pre-2001 is not available online; user scoped corpus to FY 2001+.
    def keep(r):
        fy = r.get("fiscal_year") or ""
        m = re.match(r"FY(\d{4})", fy)
        if not m:
            return True
        return int(m.group(1)) >= 2001

    filtered = [r for r in records if keep(r)]
    out2 = OUT_DIR / "inventory.json"
    out2.write_text(json.dumps(filtered, indent=2))
    print(f"wrote {len(filtered)} filtered (>= FY2001) -> {out2}")


if __name__ == "__main__":
    main()
