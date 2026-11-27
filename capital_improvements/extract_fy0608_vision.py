#!/usr/bin/env python3
"""Extract CIP projects from FY06-08 book using Claude vision via claude CLI.

Uses `claude -p` (subscription auth, no API key needed).
Replaces the 390-line EasyOCR + regex pipeline with direct vision extraction.
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
PAGES_DIR = HERE / "raw_pdfs" / "FY0608_pages"
OUTPUT = HERE / "fy0608_cip_projects.json"

SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "skip": {"type": "boolean", "description": "true if not a project page"},
        "project_name": {"type": "string"},
        "description": {"type": "string"},
        "department": {"type": "string"},
        "funding_sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "five_year_total": {"type": "integer"},
                    "fy06_07": {"type": "integer"},
                    "fy07_08": {"type": "integer"},
                    "fy08_09": {"type": "integer"},
                    "fy09_10": {"type": "integer"},
                    "fy10_11": {"type": "integer"},
                },
                "required": ["source", "five_year_total", "fy06_07", "fy07_08", "fy08_09", "fy09_10", "fy10_11"],
                "additionalProperties": False,
            },
        },
        "project_costs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "five_year_total": {"type": "integer"},
                    "fy06_07": {"type": "integer"},
                    "fy07_08": {"type": "integer"},
                    "fy08_09": {"type": "integer"},
                    "fy09_10": {"type": "integer"},
                    "fy10_11": {"type": "integer"},
                },
                "required": ["category", "five_year_total", "fy06_07", "fy07_08", "fy08_09", "fy09_10", "fy10_11"],
                "additionalProperties": False,
            },
        },
        "type_of_project": {"type": "string"},
        "operating_budget_impact": {"type": "string"},
    },
    "required": ["skip", "project_name", "description", "department",
                  "funding_sources", "project_costs", "type_of_project",
                  "operating_budget_impact"],
    "additionalProperties": False,
})

PROMPT_TEMPLATE = (
    "Read the image at {image_path}. "
    "Extract the CIP project data from this page. "
    "If this is not a project page (cover, chart, summary table, blank), set skip to true and leave other fields empty. "
    "Dollar amounts as whole integers, no cents. Zero if cell is blank or dash."
)

# Active-transportation heuristic v3
AT_SINGLE = [
    "bike", "bicycle", "bicyclist", "bicycles", "pedestrian", "pedestrians",
    "sidewalk", "sidewalks", "crosswalk", "crosswalks", "trail", "trails",
    "greenway", "bikeway", "bikeways", "rrfb", "srts",
]
AT_PHRASES = [
    "buffered lane", "hawk signal", "complete streets", "safe routes",
    "active transportation", "ada ramp", "pedestrian bridge",
    "pedestrian crossing", "traffic calming", "speed control",
    "school zone", "rail trail", "bike path", "bike lane",
]
AT_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, AT_SINGLE)) + r")\b", re.I)


def at_classify(text: str) -> tuple[bool, list[str]]:
    t = (text or "").lower()
    hits = {m.group(0) for m in AT_RE.finditer(t)}
    hits |= {k for k in AT_PHRASES if k in t}
    return bool(hits), sorted(hits)


def parse_result_json(raw: str) -> dict:
    """Extract JSON from claude -p output, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def extract_page(image_path: Path) -> dict | None:
    prompt = PROMPT_TEMPLATE.format(image_path=image_path)
    result = subprocess.run(
        ["claude", "-p", prompt,
         "--model", "haiku",
         "--json-schema", SCHEMA,
         "--tools", "Read",
         "--output-format", "json",
         "--no-session-persistence"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr[:200]}")

    envelope = json.loads(result.stdout)
    data = parse_result_json(envelope["result"])

    if data.get("skip"):
        return None
    return data


def validate_funding(project: dict) -> list[str]:
    warnings = []
    for src in project.get("funding_sources", []):
        yearly = sum(src[k] for k in ["fy06_07", "fy07_08", "fy08_09", "fy09_10", "fy10_11"])
        if yearly != src["five_year_total"]:
            warnings.append(f"funding '{src['source']}' sum={yearly} != total={src['five_year_total']}")
    return warnings


def main():
    pages = sorted(PAGES_DIR.glob("p*.png"))
    pages = [p for p in pages if int(p.stem[1:]) >= 8]
    print(f"Processing {len(pages)} pages (p008-p080) via claude -p...")

    projects = []
    for page in pages:
        num = int(page.stem[1:])
        print(f"  p{num:03d}", end="", flush=True)

        try:
            result = extract_page(page)
        except Exception as e:
            print(f" ERROR: {e}")
            continue

        if result is None:
            print(" skip")
            continue

        result["page"] = num
        blob = f"{result['project_name']} {result['description']} {result['type_of_project']}"
        result["likely_active_transportation"], result["at_keywords_matched"] = at_classify(blob)

        warnings = validate_funding(result)
        for w in warnings:
            print(f" ⚠ {w}", end="")

        projects.append(result)
        print(f" ✓ {result['project_name'][:50]}")

    output = {
        "source": "City of Oceanside — FY 2006-2008 Capital Improvement Program (5-year plan FY 06-07 through FY 10-11)",
        "source_pdf": "raw_pdfs/FY0608_CIP_section.pdf",
        "extraction_method": "Claude vision (haiku) via claude CLI — structured JSON output",
        "extracted_project_count": len(projects),
        "projects": projects,
    }
    OUTPUT.write_text(json.dumps(output, indent=2))
    print(f"\n{len(projects)} projects → {OUTPUT}")

    at_count = sum(1 for p in projects if p["likely_active_transportation"])
    print(f"Active-transportation: {at_count} projects")


if __name__ == "__main__":
    main()
