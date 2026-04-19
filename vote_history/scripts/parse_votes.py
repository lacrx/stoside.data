"""
Parse Oceanside City Council "Action Minutes" PDFs into a structured votes CSV.

Two format eras are handled:
  Format A (pre-Oct 2024, scanned Word docs):
      Motion: <Name>
      Second: <Name>
      Approved: N-M  [ (Dissenter - No) ]

  Format B (Oct 2024 onward, Legistar "Clerk's Action Minutes"):
      RESULT: APPROVED
      MOVER: <Full Name>
      SECONDER: <Full Name>
      Aye: ...
      Nay: ...
      Abstain: ...
      (also may contain older-style MOTION/SECOND/APPROVED lines mixed in)

Usage:
    python parse_votes.py                      # parse all PDFs
    python parse_votes.py --debug <filename>   # verbose dump for one PDF
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent  # .../vote_history
PDF_DIR = ROOT / "pdfs"
OUT_CSV = ROOT / "votes.csv"
LOG_PATH = ROOT / "parse_log.txt"
MEETINGS_JSON = ROOT / "meetings.json"


# ---------------------------------------------------------------------------
# Known member names and last-name normalisation
# ---------------------------------------------------------------------------
# Seed list of last names; we also discover new ones dynamically from
# "Present:" roll-call lines.
SEED_LAST_NAMES = ["SANCHEZ", "KEIM", "JOYCE", "ROBINSON", "WEISS"]

# Map first name -> likely last name for members we know about
# (used when Format B Aye list uses "Council Member Figueroa" etc.)
FIRST_TO_LAST = {
    "ESTHER": "SANCHEZ",
    "RYAN": "KEIM",
    "ERIC": "JOYCE",
    "RICK": "ROBINSON",
    "PETER": "WEISS",
    "JIMMY": "FIGUEROA",
}


def normalize_token(tok: str) -> str:
    """Uppercase and strip punctuation/accents; '-' retained for hyphenated."""
    tok = tok.strip().strip(",.;:()")
    # normalise curly apostrophes etc.
    tok = tok.replace("\u2019", "'").replace("\u2018", "'")
    return tok.upper()


# Words to skip when scanning a Present/Aye/etc. list for names
TITLE_TOKENS = {
    "MAYOR", "DEPUTY", "COUNCIL", "COUNCILMEMBER", "COUNCILMEMBERS",
    "MEMBER", "MEMBERS", "PRESIDENT", "VICE", "CHAIR", "DIRECTOR",
    "DIRECTORS", "SECRETARY", "COMMISSIONER", "COMMISSIONERS", "TREASURER",
    "AND", "THE",
}

# Common first/middle names we see tied to seated council members.
# Plus any new ones we discover at runtime via learn_first_name().
KNOWN_FIRST_NAMES = set(FIRST_TO_LAST.keys())


def extract_last_names_from_rollcall(text_fragment: str) -> List[str]:
    """Pull last names from a "Present:"/"Absent:"/"Aye:" fragment by
    anchoring on titles (Mayor / Deputy Mayor / Council Member / Councilmember).

    Format B puts every name after a title. We use that to avoid picking up
    stray words. Returns de-duplicated uppercase last names, in order.

    The fragment may span multiple wrapped lines; we collapse whitespace
    first so "Council\\nMember Joyce" reads as "Council Member Joyce".
    """
    cleaned = re.sub(r"\s+", " ", text_fragment).strip()
    cleaned = re.sub(r"\s*,\s*", " , ", cleaned)  # help token boundaries
    names: List[str] = []
    # Scan for "<title> [First [Middle]] Last" triples.
    title_re = re.compile(
        r"(?:Mayor|Deputy\s+Mayor|Council\s+Member|Council\s*member|"
        r"Councilman|Councilwoman|Councilmember)\s+"
        r"(?:([A-Z][a-zA-Z\-']+\.?)\s+)?"      # optional first/initial
        r"(?:([A-Z]\.)\s+)?"                    # optional middle initial
        r"([A-Z][a-zA-Z\-']+)"                  # last
    )
    for m in title_re.finditer(cleaned):
        last = m.group(3).upper()
        first = (m.group(1) or "").strip().rstrip(".")
        if first and not first.endswith(".") and len(first) > 1:
            learn_first_name(first, last)
        if last in {"MAYOR", "MEMBER", "COUNCIL", "DEPUTY"}:
            continue
        if last not in names:
            names.append(last)
    return names


def extract_last_names(text_fragment: str, roster: set) -> List[str]:
    """Pull a list of last-name tokens out of a "Present:" / "Aye:" fragment.

    We scan tokens; if a token is an all-letters word and not a title, and
    not a known first name, it's a candidate last name. We also allow a
    known first name to resolve via FIRST_TO_LAST.
    """
    # Replace commas/newlines with spaces, then tokenise on whitespace.
    cleaned = re.sub(r"[\r\n]+", " ", text_fragment)
    cleaned = cleaned.replace(",", " ")
    tokens = [normalize_token(t) for t in cleaned.split() if t.strip()]
    names: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok or not re.match(r"^[A-Z][A-Z'\-]+$", tok):
            i += 1
            continue
        if tok in TITLE_TOKENS:
            i += 1
            continue
        # If tok is a first name we know, use the canonical last name.
        # BUT if tok is ALSO a known last name, trust that — don't
        # resolve it through FIRST_TO_LAST (avoids polluted mappings).
        if tok in FIRST_TO_LAST and tok not in FIRST_TO_LAST.values() \
                and tok not in SEED_LAST_NAMES:
            names.append(FIRST_TO_LAST[tok])
            if i + 1 < len(tokens) and tokens[i + 1] == FIRST_TO_LAST[tok]:
                i += 2
            else:
                i += 1
            continue
        # otherwise treat as last name candidate
        names.append(tok)
        i += 1
    # Deduplicate while preserving order
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def learn_first_name(first: str, last: str) -> None:
    """Remember a first->last mapping we saw in a PDF. Defensive: never
    allow a known council LAST name to be registered as a first name, and
    never overwrite an existing entry.
    """
    first_u = first.upper()
    last_u = last.upper()
    if not first_u or not last_u:
        return
    # Don't let a last name get reclassified as a first name.
    if first_u in SEED_LAST_NAMES or first_u in FIRST_TO_LAST.values():
        return
    # Don't allow ALL-CAPS section-word collisions
    if first_u in {"GENERAL", "CONSENT", "CALENDAR", "ITEMS", "ITEM", "PAGE",
                   "PUBLIC", "STAFF", "CITY", "COUNCIL", "MEMBER", "MAYOR",
                   "DEPUTY", "BUSINESS", "SPOTLIGHT", "MOTION", "SECOND",
                   "APPROVED", "DENIED", "FAILED", "RESOLUTION", "INVOCATION",
                   "PLEDGE", "CALL", "ROLL"}:
        return
    if last_u in {"MAYOR", "MEMBER", "COUNCIL"}:
        return
    if first_u not in FIRST_TO_LAST:
        FIRST_TO_LAST[first_u] = last_u
    KNOWN_FIRST_NAMES.add(first_u)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------
def load_pdf_text(pdf_path: Path) -> str:
    """Return concatenated page text for the PDF."""
    parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for p in pdf.pages:
            t = p.extract_text() or ""
            parts.append(t)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Roll-call parsing
# ---------------------------------------------------------------------------
PRESENT_RE = re.compile(r"Present\s*:\s*(.+?)(?:\n\s*(?:Absent|Excused|INVOCATION|PLEDGE|PROCLAMATION|CLOSED|CITY|CONSENT|\d|$))",
                        re.IGNORECASE | re.DOTALL)
ABSENT_RE  = re.compile(r"(?:Absent|Excused)\s*:\s*(.+?)(?:\n\s*(?:Absent|Excused|INVOCATION|PLEDGE|PROCLAMATION|CLOSED|CITY|CONSENT|\d|$))",
                        re.IGNORECASE | re.DOTALL)


ALL_PRESENT_RE = re.compile(r"ROLL\s*CALL\s*[\u2013\-\u2014]+\s*All\s+present",
                            re.IGNORECASE)


def parse_roll_call(text: str) -> Tuple[List[str], List[str]]:
    """Return (present_last_names, absent_last_names) for the meeting.

    We look at the first "Present:" (prefer the 5:00pm one) and any "Absent:"
    or "Excused:" adjacent to it.

    In Format A some PDFs just say "ROLL CALL - All present" and list the
    councilmembers elsewhere. In that case we return ("ALL_PRESENT", []) as
    a sentinel; the caller fills in with the current-term member list.
    """
    # Prefer the roll-call chunk near "5:00 P.M." if present; otherwise
    # use the first Present: in the doc.
    present_names: List[str] = []
    absent_names: List[str] = []

    # Strategy: find all blocks that start with Present: and grab the one
    # that looks like a council list (has Mayor or Council Member tokens).
    # Using a simpler search — iterate over Present: matches.
    for m in re.finditer(r"Present\s*:", text, re.IGNORECASE):
        # grab the lines following until we hit a blank line or a known
        # next-section header
        start = m.end()
        # take up to ~400 chars after "Present:"
        chunk = text[start:start + 600]
        # cut at common section breakers
        for stop in ["INVOCATION", "PLEDGE", "PROCLAMATION", "CLOSED SESSION",
                     "CONSENT", "ROLL CALL", "CITY COUNCIL,"]:
            idx = chunk.upper().find(stop)
            if idx != -1:
                chunk = chunk[:idx]
                break
        # also stop at a line that starts with "Absent" or "Excused"
        ab_match = re.search(r"\n\s*(Absent|Excused)\s*:\s*(.+)", chunk, re.IGNORECASE)
        absent_chunk = ""
        if ab_match:
            absent_chunk = ab_match.group(2)
            chunk = chunk[:ab_match.start()]
        candidates = extract_last_names_from_rollcall(chunk)
        # plausibility: need 3-6 names, all short alpha
        if 2 <= len(candidates) <= 8:
            present_names = candidates
            if absent_chunk:
                absent_names = extract_last_names_from_rollcall(absent_chunk)
            break
    # Fall back: look for any "Absent" / "Excused" blocks if we didn't get one
    if not absent_names:
        for m in re.finditer(r"(?:Absent|Excused)\s*:\s*(.+?)(?:\n|$)",
                             text[:5000], re.IGNORECASE):
            cand = extract_last_names_from_rollcall(m.group(1))
            if cand:
                absent_names = cand
                break
    # Try to learn first-name mappings from an explicit Present: list in
    # Format B PDFs. Those contain "Council Member <First> <Last>" triples
    # on single lines. We deliberately restrict to the exact format to
    # avoid picking up noise. Use [^\S\n] (= whitespace without newline)
    # so we stay on one line.
    for m in re.finditer(
        r"(?:Mayor|Deputy[^\S\n]+Mayor|Council[^\S\n]+Member|"
        r"Councilmember|Councilwoman|Councilman)[^\S\n]+"
        r"([A-Z][a-z]+(?:[^\S\n]+[A-Z]\.)?)[^\S\n]+"
        r"([A-Z][a-z][a-zA-Z'\-]+)",
        text[:5000]
    ):
        first_tok = m.group(1).split()[0]
        last_tok = m.group(2)
        # skip if second group looks like another title word
        if last_tok.lower() in {"mayor", "member", "council"}:
            continue
        learn_first_name(first_tok, last_tok)

    # Format A "All present" fallback. Extract names from the title page
    # (which lists "Esther Sanchez  Ryan Keim" / "Eric Joyce  Zeb Navarro"
    # / "Rick Robinson" / "Peter Weiss  City Treasurer" in a block near the
    # top). We use FIRST_TO_LAST to filter to council first names, and look
    # only at single-line pairs.
    if not present_names and ALL_PRESENT_RE.search(text):
        top = text[:3500]
        cand = []
        # Walk pair candidates on each line (not crossing newlines).
        for line in top.split("\n"):
            for m in re.finditer(
                r"\b([A-Z][a-z]+(?:\s[A-Z]\.)?)\s+([A-Z][a-z][a-zA-Z'\-]+)\b",
                line,
            ):
                first = m.group(1).split()[0].upper()
                last = m.group(2).upper()
                if first in {"DEPUTY", "COUNCIL", "COUNCILMEMBER", "MAYOR",
                             "MEMBER"}:
                    continue
                if last in {"MAYOR", "MEMBER", "COUNCIL"}:
                    continue
                if first in FIRST_TO_LAST and FIRST_TO_LAST[first] == last:
                    cand.append(last)
                elif first in FIRST_TO_LAST:
                    # known first name but different last - trust the seed
                    cand.append(FIRST_TO_LAST[first])
                elif last in SEED_LAST_NAMES:
                    cand.append(last)
        # dedupe while preserving order
        seen = set()
        for c in cand:
            if c not in seen:
                seen.add(c)
                present_names.append(c)

    # Format A absent via "<Title> X absent" at top of agenda.
    # Only scan text BEFORE the first "Present:" roll-call block, so we don't
    # pick up stray "MAYOR X ABSENT" notes from closed-session narrative.
    if not absent_names:
        present_match = re.search(r"Present\s*:", text, re.IGNORECASE)
        scan_end = present_match.start() if present_match else min(3000, len(text))
        for m in re.finditer(
            r"(?:Mayor|Deputy\s+Mayor|Councilmember|Council\s+Member)\s+"
            r"([A-Z][a-zA-Z'\-]+)\s+absent",
            text[:scan_end], re.IGNORECASE,
        ):
            last = m.group(1).upper()
            if last in TITLE_TOKENS:
                continue
            if last not in absent_names:
                absent_names.append(last)
            if last in present_names:
                present_names.remove(last)

    return present_names, absent_names


# ---------------------------------------------------------------------------
# Vote block parsing
# ---------------------------------------------------------------------------
OUTCOME_TERMS = [
    "APPROVED", "DENIED", "FAILED", "FAILS", "PASSED", "CARRIED", "DEFEATED",
    "TABLED", "CONTINUED", "ADOPTED", "REJECTED", "INTRODUCED", "WITHDRAWN",
]

# Format A patterns
A_ITEM_NUM_RE   = re.compile(r"^\s*(\d+)\.\s+(.+)", re.MULTILINE)
# "Motion: Name" standard line
A_MOTION_RE     = re.compile(r"^\s*Motion\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
# "Motion to <summary>...: Name" (inline mover after colon, possibly wrapping).
# Handles any mix of case. The summary part is capped to avoid backtracking.
A_MOTION_INLINE_RE = re.compile(
    r"MOTION\s+(?:TO|THAT)\s+([^:]{1,500}?)\s*:\s*"
    r"([A-Z][A-Za-z'\-]+)\s*\n",
    re.IGNORECASE,
)
A_SECOND_RE     = re.compile(r"^\s*Second\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
A_OUTCOME_RE    = re.compile(
    r"^\s*(?:(?:The\s+)?Motion\s+)?"         # optional "Motion " / "The Motion " prefix
    r"(Approved|Denied|Failed|Fails|Passed|Carried|Defeated|Tabled|Continued|Adopted|Rejected|Withdrawn)\s*:\s*"
    r"(\d+)\s*[-\u2013]\s*(\d+)"
    r"(?:\s*[-\u2013]\s*\d+)?"              # optional 3rd number = abstain count (non-capturing; dissenter_parse recovers names)
    r"(?:\s*\(([^)\n]+(?:\n[^)\n]+)?)\))?",   # optional parenthetical (may wrap 1 line)
    re.IGNORECASE | re.MULTILINE,
)
# Motion to approve consent calendar items X-Y, Z-W
A_CONSENT_RE    = re.compile(
    r"Motion\s+to\s+Approve\s+Consent\s+Calendar\s+Items?\s+([0-9,\-\s&]+)",
    re.IGNORECASE,
)
# Format A "die for lack of second"
A_DIES_RE = re.compile(r"Motion\s+dies\s+for\s+lack\s+of\s+(?:a\s+)?second",
                       re.IGNORECASE)

# Hybrid/Legistar shorthand style (appears in 2024-2025 Format B as well).
# The mover/seconder segment must be an UPPERCASE name (often a last name);
# not case-insensitive so we don't accidentally match Format A "Motion: Keim".
# The "TO <summary>" clause is allowed and can span up to ~500 chars.
H_MOTION_RE = re.compile(
    r"MOTION(?:\s+(?:TO|THAT)[^:]{0,500})?\s*:\s*"
    r"([A-Z][A-Z'\-\s/&,]*?)\s*\n"
    r"\s*SECOND\s*:\s*([A-Z][A-Z'\-\s/&,]*?)\s*\n"
    r"\s*(?:MOTION\s+)?"                   # optional "MOTION " prefix before outcome (e.g., "MOTION FAILED:")
    r"(APPROVED|DENIED|FAILED|FAILS|PASSED|CARRIED|DEFEATED|TABLED|CONTINUED|ADOPTED|REJECTED|WITHDRAWN)\s*:\s*"
    r"(\d+)\s*[-\u2013]\s*(\d+)"
    r"(?:\s*[-\u2013]\s*\d+)?"              # optional 3rd number (abstain count); index remains stable because we don't capture it
    r"(?:\s*\(([^)\n]+(?:\n[^)\n]+)?)\))?",
)
# consent calendar variant "MOTION TO APPROVE ITEMS 2-3, 5-9: NAME"
# Uppercase-only so we don't collide with Format A "Motion to Approve Consent Calendar Items ..."
H_CONSENT_RE = re.compile(
    r"MOTION\s+TO\s+APPROVE\s+(?:CONSENT\s+CALENDAR\s+)?ITEMS?\s*#?\s*([0-9,\-\s&]+?)\s*:",
)

# Format B block-style patterns
B_RESULT_RE   = re.compile(r"^\s*RESULT\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
B_MOVER_RE    = re.compile(r"^\s*MOVER\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
B_SECONDER_RE = re.compile(r"^\s*SECONDER\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
B_AYE_RE      = re.compile(r"^\s*Aye\s*:\s*(.+?)(?=^\s*(?:Nay|Abstain|Absent|Excused|Enactment|RESULT|MOVER|SECONDER|A\)|B\)|ADOPTION|GENERAL|PUBLIC|MAYOR|CITY|CONSENT|ADJOURNMENT|CLOSED|PROCLAMATIONS|INVOCATION|PLEDGE|Page|ITEM|MOTION|WORKSHOP|REPORT|\d+\.|$))",
                           re.IGNORECASE | re.MULTILINE | re.DOTALL)
B_NAY_RE      = re.compile(r"^\s*Nay\s*:\s*(.+?)(?=^\s*(?:Nay|Abstain|Absent|Excused|Enactment|RESULT|MOVER|SECONDER|A\)|B\)|ADOPTION|GENERAL|PUBLIC|MAYOR|CITY|CONSENT|ADJOURNMENT|CLOSED|PROCLAMATIONS|INVOCATION|PLEDGE|Page|ITEM|MOTION|WORKSHOP|REPORT|\d+\.|$))",
                           re.IGNORECASE | re.MULTILINE | re.DOTALL)
B_ABSTAIN_RE  = re.compile(r"^\s*Abstain\s*:\s*(.+?)(?=^\s*(?:Nay|Abstain|Absent|Excused|Enactment|RESULT|MOVER|SECONDER|A\)|B\)|ADOPTION|GENERAL|PUBLIC|MAYOR|CITY|CONSENT|ADJOURNMENT|CLOSED|PROCLAMATIONS|INVOCATION|PLEDGE|Page|ITEM|MOTION|WORKSHOP|REPORT|\d+\.|$))",
                           re.IGNORECASE | re.MULTILINE | re.DOTALL)
B_ABSENT_RE   = re.compile(r"^\s*(?:Absent|Excused)\s*:\s*(.+?)(?=^\s*(?:Nay|Abstain|Absent|Excused|Enactment|RESULT|MOVER|SECONDER|A\)|B\)|ADOPTION|GENERAL|PUBLIC|MAYOR|CITY|CONSENT|ADJOURNMENT|CLOSED|PROCLAMATIONS|INVOCATION|PLEDGE|Page|ITEM|MOTION|WORKSHOP|REPORT|\d+\.|$))",
                           re.IGNORECASE | re.MULTILINE | re.DOTALL)


# ---------------------------------------------------------------------------
# Utility: parse item-number ranges like "4-5, 9-20" into a list of ints
# ---------------------------------------------------------------------------
def expand_item_ranges(spec: str) -> List[int]:
    """'4-5, 9-20' -> [4,5,9,10,11,...,20]  (also '4 & 6', '#2-3, 5')."""
    nums: List[int] = []
    spec = spec.replace("&", ",").replace("#", "")
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part or "\u2013" in part:
            seg = re.split(r"[-\u2013]", part)
            try:
                lo = int(seg[0].strip())
                hi = int(seg[-1].strip())
                if lo <= hi <= lo + 60:
                    nums.extend(range(lo, hi + 1))
            except ValueError:
                pass
        else:
            try:
                nums.append(int(part))
            except ValueError:
                pass
    return nums


# ---------------------------------------------------------------------------
# Item detection
# ---------------------------------------------------------------------------
ITEM_HEADER_RE = re.compile(
    r"^\s*(\d{1,3})\.\s+(.{3,400}?)\s*$",
    re.MULTILINE,
)


def split_into_items(text: str) -> List[Tuple[int, str, str]]:
    """Return list of (item_number, item_title_first_line, body_text).

    body_text runs from the item header to the next item header (or end).
    """
    # Find all candidate "N." line starts. Not every match is a real agenda
    # item, but the vote parsing logic below naturally skips ones with no
    # motion/outcome.
    matches = list(ITEM_HEADER_RE.finditer(text))
    items = []
    for idx, m in enumerate(matches):
        num = int(m.group(1))
        title_first_line = m.group(2).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end]
        items.append((num, title_first_line, body))
    return items


def dissenter_parse(paren_text: str) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Parse "(Joyce - No)" / "(Robinson recused)" / "(Weiss stepped out)".

    Return (no_names, abstain_names, absent_names, other_names_unclassified).
    Recognises several idioms:
      - "X - No" / "X - Abstain" (dash-separated)
      - "X recused" / "X - recused" (recused → treated as Abstain)
      - "X - ABSENT" / "X absent"
      - "X stepped out" / "X stepped out of the room" → Absent for this vote
    """
    no_n, abs_n, ab_n, other = [], [], [], []
    # split on ';'
    for chunk in re.split(r"[;]", paren_text):
        chunk = chunk.strip()
        if not chunk:
            continue

        # Normalise fancy dashes to a plain hyphen to simplify patterns.
        norm = re.sub(r"[\u2013\u2014]", "-", chunk)

        # Pattern 1: "NAMES - LABEL [prose]"
        mm = re.match(
            r"(.+?)\s*-\s*(No|Yes|Aye|Nay|Abstain|Abstained|Absent|Excused|Recused)\b",
            norm, re.IGNORECASE,
        )
        if mm:
            names_str, label = mm.group(1), mm.group(2).lower()
            names = extract_last_names(names_str, set())
            if label in ("no", "nay"):
                no_n.extend(names)
            elif label.startswith("abstain") or label == "recused":
                abs_n.extend(names)
            elif label in ("absent", "excused"):
                ab_n.extend(names)
            continue

        # Pattern 2: "NAMES recused/abstained/stepped out/absent" (no dash)
        mm = re.match(
            r"(.+?)\s+(recused|abstained|stepped\s+out(?:\s+of\s+the\s+room)?"
            r"(?:\s+during\s+the\s+vote)?|absent)\b",
            norm, re.IGNORECASE,
        )
        if mm:
            names_str = mm.group(1)
            label = mm.group(2).lower()
            names = extract_last_names(names_str, set())
            if label.startswith("recused") or label.startswith("abstain"):
                abs_n.extend(names)
            elif label.startswith("stepped") or label == "absent":
                ab_n.extend(names)
            continue

        other.append(chunk)
    return no_n, abs_n, ab_n, other


def outcome_normalize(raw: str) -> str:
    """Normalise outcome token (case-insensitive, strip punctuation)."""
    r = raw.strip().upper().rstrip(".:")
    # "APPROVED THE CONSENT AGENDA" -> APPROVED
    for kw in OUTCOME_TERMS:
        if r.startswith(kw):
            # Collapse present-tense "FAILS" to past-tense "FAILED"
            return "FAILED" if kw == "FAILS" else kw
    return r


# ---------------------------------------------------------------------------
# Build a vote dict for one item
# ---------------------------------------------------------------------------
def resolve_members(
    present: List[str],
    absent: List[str],
    ayes: List[str],
    nays: List[str],
    abstains: List[str],
    count_for: Optional[int],
    count_against: Optional[int],
    member_roster: List[str],
    member_currently_seated: set,
    vote_absent: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """Return per-member vote dict + list of notes/warnings.

    vote_absent lists members who were present overall but stepped out for
    this specific vote (e.g., "(Weiss stepped out)"). They're marked Absent
    for this row.
    """
    notes: List[str] = []
    out: Dict[str, str] = {}

    explicit_ayes   = set(ayes)
    explicit_nays   = set(nays)
    explicit_absts  = set(abstains)
    vote_absent_set = set(vote_absent or [])

    # Only if we have an explicit Aye list (Format B) do we treat the vote
    # block as fully enumerated. Format A often lists only dissenters in a
    # parenthetical with a numeric count; in that case we still infer.
    have_explicit_lists = bool(explicit_ayes)

    for m in member_roster:
        if m not in member_currently_seated:
            out[m] = "NotOnCouncil"
            continue
        # On the council that term. Is the member Present today?
        is_present = m in present and m not in absent
        if m in vote_absent_set:
            out[m] = "Absent"
            continue
        if m in explicit_nays:
            out[m] = "No"
        elif m in explicit_absts:
            out[m] = "Abstain"
        elif m in explicit_ayes:
            out[m] = "Yes"
        elif not is_present:
            out[m] = "Absent"
        else:
            # Present but not named explicitly in Aye/Nay/Abstain:
            if have_explicit_lists:
                # Format B: if Aye: list exists but this person isn't in it
                # and isn't listed elsewhere, call them Unknown (or Absent if
                # they were never present). Typically the Aye list is
                # exhaustive for those present.
                out[m] = "Unknown"
            else:
                # Format A: infer from count.
                out[m] = "PENDING"  # fill below

    # Format A inference: we have count_for / count_against and explicit nays
    # (possibly via parenthetical dissenters). Everyone else Present -> Yes,
    # validated against count_for.
    if not have_explicit_lists and count_for is not None and count_against is not None:
        # We've set nays via dissenter parse if any.
        seated_present = [m for m in member_roster
                          if m in member_currently_seated and m in present
                          and m not in absent and m not in vote_absent_set]
        non_nay_present = [m for m in seated_present
                           if out.get(m) not in ("No", "Abstain", "Absent")]
        expected_yes = count_for
        expected_no  = count_against
        # If explicit dissenters matched:
        actual_no = sum(1 for v in out.values() if v == "No")
        actual_abstain = sum(1 for v in out.values() if v == "Abstain")
        # expected yes = len(non_nay_present) if the math adds up
        if (len(non_nay_present) == expected_yes
            and actual_no == expected_no):
            for m in non_nay_present:
                out[m] = "Yes"
        else:
            # Can't cleanly reconcile; mark PENDING as Unknown.
            notes.append(
                f"Count mismatch: reported {expected_yes}-{expected_no}, "
                f"present={len(seated_present)}, explicit_no={actual_no}, "
                f"explicit_abstain={actual_abstain}"
            )
            for m in member_roster:
                if out.get(m) == "PENDING":
                    out[m] = "Unknown"
    else:
        # replace any leftover PENDING
        for m in member_roster:
            if out.get(m) == "PENDING":
                out[m] = "Unknown"

    return out, notes


# ---------------------------------------------------------------------------
# Main parse per PDF
# ---------------------------------------------------------------------------
def parse_pdf(
    pdf_path: Path,
    meeting_date: str,
    meeting_id: str,
    member_roster: List[str],
    debug: bool = False,
    present_override: Optional[List[str]] = None,
    absent_override: Optional[List[str]] = None,
) -> Tuple[List[dict], List[str]]:
    """Return (votes, log_messages)."""
    log: List[str] = []
    try:
        text = load_pdf_text(pdf_path)
    except Exception as e:
        log.append(f"[{pdf_path.name}] FAILED to extract text: {e}")
        return [], log

    # Detect format
    is_format_b = bool(re.search(r"\bClerk'?s Action Minutes\b", text)
                       or re.search(r"\bRESULT\s*:\s*", text))
    fmt = "B" if is_format_b else "A"

    if present_override is not None:
        present, absent = present_override, (absent_override or [])
    else:
        present, absent = parse_roll_call(text)
    if debug:
        print(f"--- {pdf_path.name} [format {fmt}] ---")
        print(f"Present: {present}")
        print(f"Absent:  {absent}")

    # roster for this meeting: present + absent (those we know were seated)
    seated = set(present) | set(absent)
    # If we know a member always served during this date range, include them
    # even if we failed to pick them up. But keep conservative: if we saw no
    # present list, we can't accurately tell; seated remains what we found.

    items = split_into_items(text)
    votes: List[dict] = []

    # ---------------------------------------------------------------------
    # 1) Find consent batches. A consent batch is a single motion covering
    # multiple items. We parse these specially so each covered item gets a
    # row with the batch's vote attached.
    # ---------------------------------------------------------------------
    consent_batches: List[Tuple[List[int], dict]] = []

    # Helper: determine which agenda item CONTAINS a given text offset.
    def _item_at(pos: int) -> Optional[int]:
        # Find the item header whose start_pos <= pos < next start_pos.
        last_num = None
        last_start = 0
        for hm in ITEM_HEADER_RE.finditer(text):
            if hm.start() > pos:
                break
            last_num = int(hm.group(1))
            last_start = hm.start()
        if last_num is None:
            return None
        # Skip closed-session items — they're narrative, not votable, so the
        # batch motion appearing inside them is coincidental. Same for proclamations.
        body_sample = text[last_start:last_start + 400].upper()
        if ("CONFERENCE WITH LABOR" in body_sample
                or "CONFERENCE WITH LEGAL" in body_sample
                or "CONFERENCE WITH REAL PROPERTY" in body_sample
                or "LITIGATION OR OTHER ADVERSARY" in body_sample
                or "INITIATION OF LITIGATION" in body_sample
                or "PUBLIC EMPLOYEE APPOINTMENT" in body_sample
                or "PUBLIC EMPLOYEE DISCIPLINE" in body_sample):
            return None
        return last_num

    # Format A consent: "Motion to Approve Consent Calendar Items X-Y, ..."
    # followed by Motion/Second/Approved lines.
    # The mover name may appear EITHER after "Items X-Y, ...: <Name>" on the
    # same block OR via a separate "Motion: <Name>" line below.
    for m in A_CONSENT_RE.finditer(text):
        items_spec = m.group(1)
        # Look at the next ~700 chars for Motion:/Second:/Approved:
        chunk_start = m.end()
        chunk = text[chunk_start:chunk_start + 700]

        # Detect "items-spec: <Name>\n...Second: ..." (early Format A).
        inline_mover_match = re.match(
            r"\s*:\s*([A-Za-z][A-Za-z'\-]*)\s*\n",
            chunk,
        )
        mo = None
        if inline_mover_match:
            mover_name = inline_mover_match.group(1)
            mo_span = (chunk_start, chunk_start + inline_mover_match.end())
            mover = extract_last_names(mover_name, set())
            # skip past the inline mover portion
            chunk = chunk[inline_mover_match.end():]
        else:
            mo = A_MOTION_RE.search(chunk)
            mover = extract_last_names(mo.group(1), set()) if mo else []
            if mo:
                chunk = chunk[mo.end():]

        se = A_SECOND_RE.search(chunk)
        oc = A_OUTCOME_RE.search(chunk)
        if (inline_mover_match or mo) and se and oc:
            seconder = extract_last_names(se.group(1), set())
            outcome_tok = outcome_normalize(oc.group(1))
            cf = int(oc.group(2))
            ca = int(oc.group(3))
            dissent = oc.group(4) or ""
            nos, absts, vabs, _ = dissenter_parse(dissent)
            nums = expand_item_ranges(items_spec)
            containing = _item_at(m.start())
            if containing is not None and containing not in nums:
                nums.append(containing)
            # Some older PDFs also implicitly cover the item right after
            # the containing item (e.g., "waive reading" + "accept minutes").
            # We don't add that blindly; it'll show up if it has an
            # "Approved:" line but no motion of its own.
            consent_batches.append((
                nums,
                {
                    "outcome": outcome_tok,
                    "count_for": cf,
                    "count_against": ca,
                    "mover": mover[0] if mover else "",
                    "seconder": seconder[0] if seconder else "",
                    "ayes": [],  # Format A doesn't enumerate
                    "nays": nos,
                    "abstains": absts,
                    "vote_absent": vabs,
                    "motion_summary": "Approve Consent Calendar",
                    "fmt": "A",
                    "batch_label": f"consent batch for items {items_spec.strip()}",
                }
            ))

    # Hybrid/legistar shorthand consent: "MOTION TO APPROVE ITEMS 2-3, 5-9: ..."
    for m in H_CONSENT_RE.finditer(text):
        items_spec = m.group(1)
        # If preceded by lowercase "Motion to Approve" Format A wording, skip here
        # (caught separately by A_CONSENT_RE).
        if not re.match(r"^[A-Z ]", m.group(0)):
            continue
        # From this point find the matching H_MOTION_RE nearby (should be same block)
        window = text[m.start():m.start() + 800]
        hm = H_MOTION_RE.search(window)
        if hm:
            outcome_tok = outcome_normalize(hm.group(3))
            cf = int(hm.group(4))
            ca = int(hm.group(5))
            dissent = hm.group(6) or ""
            nos, absts, vabs, _ = dissenter_parse(dissent)
            mover = extract_last_names(hm.group(1), set())
            seconder = extract_last_names(hm.group(2), set())
            nums = expand_item_ranges(items_spec)
            containing = _item_at(m.start())
            if containing is not None and containing not in nums:
                nums.append(containing)
            # avoid duplicating an already-added consent batch
            already = any(set(b[0]) == set(nums) for b in consent_batches)
            if not already:
                consent_batches.append((
                    nums,
                    {
                        "outcome": outcome_tok,
                        "count_for": cf,
                        "count_against": ca,
                        "mover": mover[0] if mover else "",
                        "seconder": seconder[0] if seconder else "",
                        "ayes": [],
                        "nays": nos,
                        "abstains": absts,
                        "vote_absent": vabs,
                        "motion_summary": "Approve Consent Items",
                        "fmt": "hybrid",
                        "batch_label": f"consent batch for items {items_spec.strip()}",
                    }
                ))

    # index: item number -> list of batches that cover it
    covered_by: Dict[int, List[dict]] = defaultdict(list)
    for nums, batch in consent_batches:
        for n in nums:
            covered_by[n].append(batch)

    # ---------------------------------------------------------------------
    # 2) Walk each item, find per-item motion data if present,
    # otherwise inherit consent batch if covered.
    # ---------------------------------------------------------------------
    for (num, title_first_line, body) in items:
        # Skip tiny "item numbers" that look like section sub-lists (body too short)
        title = title_first_line.strip()

        # Skip closed-session items entirely — their bodies often physically
        # contain the next (open-session) consent motion, which isn't theirs.
        title_upper = title.upper()
        body_head = body[:300].upper()
        if (title_upper.startswith("CONFERENCE WITH")
            or title_upper.startswith("LITIGATION OR OTHER ADVERSARY")
            or title_upper.startswith("INITIATION OF LITIGATION")
            or "CONFERENCE WITH LABOR" in body_head
            or "CONFERENCE WITH REAL PROPERTY" in body_head
            or "CONFERENCE WITH LEGAL COUNSEL" in body_head):
            continue

        # Look for Format B style vote block in body.
        b_result = B_RESULT_RE.search(body)
        b_mover  = B_MOVER_RE.search(body)
        b_sec    = B_SECONDER_RE.search(body)
        b_aye    = B_AYE_RE.search(body + "\n\n")  # ensure tail match
        b_nay    = B_NAY_RE.search(body + "\n\n")
        b_abst   = B_ABSTAIN_RE.search(body + "\n\n")
        # If we have a B_RESULT, build a vote from it.
        if b_result and (b_mover or b_sec or b_aye):
            outcome_tok = outcome_normalize(b_result.group(1))
            # Some minutes only prefix the first name with a title, e.g.
            # "Aye: Council Member Weiss, Joyce, Keim, Robinson, and Sanchez".
            # Fall back to the bare-token extractor for the remainder so all
            # five members are captured, not just the titled one.
            def _aye_names(frag: str) -> List[str]:
                a = extract_last_names_from_rollcall(frag)
                b = [n for n in extract_last_names(frag, set())
                     if n in SEED_LAST_NAMES or n in KNOWN_FIRST_NAMES
                     or n in {m.upper() for m in member_roster}]
                out = list(a)
                for n in b:
                    if n not in out:
                        out.append(n)
                return out
            ayes = _aye_names(b_aye.group(1)) if b_aye else []
            nays = _aye_names(b_nay.group(1)) if b_nay else []
            absts = _aye_names(b_abst.group(1)) if b_abst else []
            mover = b_mover.group(1).strip() if b_mover else ""
            seconder = b_sec.group(1).strip() if b_sec else ""
            # Convert full-name mover/seconder to last name
            mover_last = extract_last_names(mover, set())
            seconder_last = extract_last_names(seconder, set())
            # Update first->last mapping if we have two tokens
            for full in (mover, seconder):
                parts = full.split()
                if len(parts) >= 2:
                    learn_first_name(parts[0], parts[-1])
            motion_summary = _find_motion_summary_b(body)
            notes_extra: List[str] = []
            # If RESULT is present but there's no Aye/Nay/Abstain list at
            # all, the minutes are incomplete. For APPROVED outcome treat as
            # unanimous among Present (and log it); for others, mark Unknown.
            if not ayes and not nays and not absts:
                if outcome_tok in {"APPROVED", "ADOPTED", "PASSED", "CARRIED",
                                    "INTRODUCED"}:
                    ayes = [m for m in present if m not in absent]
                    notes_extra.append(
                        "no explicit vote list in minutes; inferred "
                        "unanimous from Present roll-call"
                    )
            cf = len(ayes) if ayes else None
            ca = len(nays) if nays else 0
            votes.append(_make_vote_row(
                meeting_date, meeting_id, pdf_path.name,
                num, title, motion_summary, outcome_tok,
                cf, ca,
                mover_last[0] if mover_last else mover,
                seconder_last[0] if seconder_last else seconder,
                ayes, nays, absts,
                present, absent, member_roster, seated,
                fmt="B",
                notes_extra=notes_extra,
            ))
            continue

        # Look for hybrid "MOTION: X / SECOND: Y / APPROVED: N-M" (possibly
        # more than one per item — items sometimes have a failed motion
        # followed by a successful amended motion, and we want both rows).
        has_consent = bool(H_CONSENT_RE.search(body))
        hm_matches = [] if has_consent else list(H_MOTION_RE.finditer(body))
        if hm_matches:
            for hm in hm_matches:
                outcome_tok = outcome_normalize(hm.group(3))
                cf = int(hm.group(4))
                ca = int(hm.group(5))
                dissent = hm.group(6) or ""
                nos, absts, vabs, _ = dissenter_parse(dissent)
                mover = extract_last_names(hm.group(1), set())
                seconder = extract_last_names(hm.group(2), set())
                motion_summary = _find_motion_summary_hybrid(body, hm.start())
                votes.append(_make_vote_row(
                    meeting_date, meeting_id, pdf_path.name,
                    num, title, motion_summary, outcome_tok,
                    cf, ca,
                    mover[0] if mover else "",
                    seconder[0] if seconder else "",
                    [], nos, absts,
                    present, absent, member_roster, seated,
                    fmt="hybrid",
                    notes_extra=[],
                    vote_absent=vabs,
                ))
            continue

        # Format A: Motion: / Second: / Approved: N-M — again iterate over
        # all outcome lines so we catch both a failed and a successful motion
        # in the same item.
        if A_CONSENT_RE.search(body):
            a_oc_matches = []
        else:
            a_oc_matches = list(A_OUTCOME_RE.finditer(body))

        a_se_list = list(A_SECOND_RE.finditer(body))
        a_mo_list = list(A_MOTION_RE.finditer(body))
        a_mo_inline_list = list(A_MOTION_INLINE_RE.finditer(body))

        emitted_any = False
        for a_oc in a_oc_matches:
            # Find the nearest preceding Motion and Second before this outcome.
            oc_pos = a_oc.start()
            a_se = next((s for s in reversed(a_se_list) if s.start() < oc_pos), None)
            a_mo = next((m for m in reversed(a_mo_list) if m.start() < oc_pos), None)
            a_mo_inline = None
            if not a_mo:
                a_mo_inline = next(
                    (m for m in reversed(a_mo_inline_list) if m.start() < oc_pos),
                    None,
                )
            if not a_se or not (a_mo or a_mo_inline):
                continue
            # Don't reuse a Motion/Second pair that's already been attached
            # to an earlier outcome in the same item (cheap guard).
            outcome_tok = outcome_normalize(a_oc.group(1))
            cf = int(a_oc.group(2))
            ca = int(a_oc.group(3))
            dissent = a_oc.group(4) or ""
            nos, absts, vabs, _ = dissenter_parse(dissent)
            if a_mo:
                mover_raw = a_mo.group(1)
                motion_summary = a_mo.group(1).strip()
                ctx = _find_motion_summary_a(body, a_mo.start())
                if ctx:
                    motion_summary = ctx
            else:
                mover_raw = a_mo_inline.group(2)
                motion_summary = "Motion to " + _tidy(a_mo_inline.group(1))
            mover = extract_last_names(mover_raw, set())
            seconder = extract_last_names(a_se.group(1), set())
            notes_extra: List[str] = []
            if not emitted_any and A_DIES_RE.search(body):
                notes_extra.append("first motion died for lack of second")
            votes.append(_make_vote_row(
                meeting_date, meeting_id, pdf_path.name,
                num, title, motion_summary, outcome_tok,
                cf, ca,
                mover[0] if mover else "",
                seconder[0] if seconder else "",
                [], nos, absts,
                present, absent, member_roster, seated,
                fmt="A",
                notes_extra=notes_extra,
                vote_absent=vabs,
            ))
            emitted_any = True
        if emitted_any:
            continue

        # No per-item motion found. Could be:
        #   - A consent item inheriting a batch vote
        #   - An orphan "Approved: 5-0" consent item (Format A)
        #   - A non-vote (presentation, etc.)
        a_oc_only = A_OUTCOME_RE.search(body)
        if a_oc_only and num in covered_by:
            batch = covered_by[num][0]
            notes_extra = [batch["batch_label"]]
            votes.append(_make_vote_row(
                meeting_date, meeting_id, pdf_path.name,
                num, title, batch["motion_summary"], batch["outcome"],
                batch["count_for"], batch["count_against"],
                batch["mover"], batch["seconder"],
                batch["ayes"], batch["nays"], batch["abstains"],
                present, absent, member_roster, seated,
                fmt=batch["fmt"],
                notes_extra=notes_extra,
                vote_absent=batch.get("vote_absent"),
            ))
            continue
        if num in covered_by:
            batch = covered_by[num][0]
            notes_extra = [batch["batch_label"]]
            votes.append(_make_vote_row(
                meeting_date, meeting_id, pdf_path.name,
                num, title, batch["motion_summary"], batch["outcome"],
                batch["count_for"], batch["count_against"],
                batch["mover"], batch["seconder"],
                batch["ayes"], batch["nays"], batch["abstains"],
                present, absent, member_roster, seated,
                fmt=batch["fmt"],
                notes_extra=notes_extra,
                vote_absent=batch.get("vote_absent"),
            ))
            continue
        # orphan Approved: line with no Motion: line — rare; skip w/ warning
        if a_oc_only:
            log.append(
                f"[{pdf_path.name}] item {num}: saw '{a_oc_only.group(0).strip()}'"
                f" but no Motion/Second and no consent batch — skipped"
            )
        # else: no motion, skip silently (presentation, proclamation, etc.)

    if debug:
        print(f"Found {len(votes)} vote(s).")
        for v in votes:
            print(f"  item {v['item_number']}: {v['outcome']} "
                  f"{v['vote_count_for']}-{v['vote_count_against']} "
                  f"by {v['mover']}/{v['seconder']}  ({v.get('__fmt')})")
            print(f"    title: {v['item_title'][:80]}")
            print(f"    members: " + ", ".join(
                f"{k}={v[k]}" for k in member_roster
            ))
            if v.get("notes"):
                print(f"    notes: {v['notes']}")

    return votes, log


# ---------------------------------------------------------------------------
# motion_summary helpers
# ---------------------------------------------------------------------------
def _find_motion_summary_a(body: str, motion_pos: int) -> str:
    """In Format A, look above the Motion: line for a motion description
    starting with 'Motion to ...', otherwise return blank."""
    before = body[:motion_pos]
    # find last "Motion to ..." line before motion_pos
    m = None
    for mm in re.finditer(r"Motion\s+to\s+([^\n]+)", before, re.IGNORECASE):
        m = mm
    if m:
        summary = m.group(0).strip()
        # trim trailing ": Name"
        summary = re.sub(r":\s*[A-Z][a-zA-Z\-']+\s*$", "", summary)
        return summary[:400]
    return ""


def _find_motion_summary_hybrid(body: str, motion_pos: int) -> str:
    before = body[:motion_pos]
    m = None
    for mm in re.finditer(r"MOTION\s+TO\s+([^\n:]+)", before, re.IGNORECASE):
        m = mm
    if m:
        return m.group(0).strip()[:400]
    return ""


def _find_motion_summary_b(body: str) -> str:
    # Look for "A motion was made by ... to <summary>. The motion ..."
    m = re.search(r"A motion was made by[^.]*?to\s+([^.]+)\.\s+The motion",
                  body, re.IGNORECASE | re.DOTALL)
    if m:
        s = m.group(1).strip()
        return re.sub(r"\s+", " ", s)[:400]
    # Or a "MOTION TO ..." header right above RESULT:
    m = re.search(r"MOTION\s+TO\s+([^\n]+)", body, re.IGNORECASE)
    if m:
        return m.group(0).strip()[:400]
    return ""


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------
def _make_vote_row(
    meeting_date: str,
    meeting_id: str,
    pdf_file: str,
    item_number: int,
    item_title: str,
    motion_summary: str,
    outcome: str,
    count_for: Optional[int],
    count_against: Optional[int],
    mover: str,
    seconder: str,
    ayes: List[str],
    nays: List[str],
    abstains: List[str],
    present: List[str],
    absent: List[str],
    member_roster: List[str],
    seated: set,
    fmt: str,
    notes_extra: List[str],
    vote_absent: Optional[List[str]] = None,
) -> dict:
    # Special case: on swearing-in meetings the first vote (election results)
    # is cast by the outgoing council — the newly elected member isn't seated
    # yet. For Dec 14, 2022 item 1, Joyce is still not-on-council (and
    # Rodriguez, the outgoing member, is absent per the roll-call).
    effective_seated = seated
    if meeting_date == "2022-12-14" and item_number == 1:
        effective_seated = {m for m in seated if m != "JOYCE"}
    per_member, warn = resolve_members(
        present=present,
        absent=absent,
        ayes=ayes,
        nays=nays,
        abstains=abstains,
        count_for=count_for,
        count_against=count_against,
        member_roster=member_roster,
        member_currently_seated=effective_seated,
        vote_absent=vote_absent,
    )
    notes = [_tidy(n) for n in (list(notes_extra) + warn) if n]
    row = {
        "meeting_date": meeting_date,
        "meeting_id": meeting_id,
        "pdf_file": pdf_file,
        "item_number": item_number,
        "item_title": _tidy(item_title),
        "motion_summary": _tidy(motion_summary),
        "outcome": outcome,
        "vote_count_for": count_for if count_for is not None else "",
        "vote_count_against": count_against if count_against is not None else "",
        "mover": mover,
        "seconder": seconder,
        "notes": "; ".join(notes),
        "__fmt": fmt,
    }
    for m in member_roster:
        row[m] = per_member.get(m, "Unknown")
    return row


def _tidy(s: str) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    return s.strip()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def collect_member_roster_and_seated(
    pdf_files: List[Path],
) -> Tuple[List[str], Dict[str, Tuple[List[str], List[str]]]]:
    """Scan all PDFs once.

    Returns:
        roster: full ordered list of member last-names observed across the
                entire dataset.
        seated_by_date: dict keyed by 'YYYY-MM-DD' -> (present, absent)
                discovered from that PDF (may be ([], []) if not found).
    """
    roster = set(SEED_LAST_NAMES)
    seated_by_date: Dict[str, Tuple[List[str], List[str]]] = {}
    for p in pdf_files:
        try:
            text = load_pdf_text(p)
        except Exception:
            continue
        present, absent = parse_roll_call(text)
        date, _ = pdf_meta_from_filename(p.name)
        seated_by_date[p.name] = (present, absent)
        for n in present + absent:
            if re.match(r"^[A-Z][A-Z'\-]{1,}$", n) and n not in TITLE_TOKENS:
                roster.add(n)
    new_names = sorted(n for n in roster if n not in SEED_LAST_NAMES)
    return SEED_LAST_NAMES + new_names, seated_by_date


def seated_roster_for_date(
    pdf_name: str,
    seated_by_date: Dict[str, Tuple[List[str], List[str]]],
) -> Tuple[List[str], List[str]]:
    """For a PDF with empty Present, borrow the roster from nearest-earlier
    PDF but keep this PDF's own Absent list. Returns (present, absent).
    """
    present, absent = seated_by_date.get(pdf_name, ([], []))
    if present:
        return present, absent
    sorted_names = sorted(seated_by_date.keys())
    try:
        idx = sorted_names.index(pdf_name)
    except ValueError:
        return present, absent
    # Borrow the full seated roster (present+absent) from a neighbour.
    borrowed: List[str] = []
    for i in range(idx - 1, -1, -1):
        p2, a2 = seated_by_date[sorted_names[i]]
        if p2:
            borrowed = list(p2) + [x for x in a2 if x not in p2]
            break
    if not borrowed:
        for i in range(idx + 1, len(sorted_names)):
            p2, a2 = seated_by_date[sorted_names[i]]
            if p2:
                borrowed = list(p2) + [x for x in a2 if x not in p2]
                break
    # present = borrowed roster minus our own absent list
    present = [m for m in borrowed if m not in absent]
    return present, absent


def pdf_meta_from_filename(name: str) -> Tuple[str, str]:
    """Extract (meeting_date, meeting_id) from 'YYYY-MM-DD_id-NNNNNNN.pdf'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})_id-(\d+)\.pdf$", name)
    if not m:
        return "", ""
    return m.group(1), m.group(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", type=str, help="filename or path of one PDF to debug-print")
    ap.add_argument("--limit", type=int, default=0, help="cap number of PDFs (for iteration)")
    args = ap.parse_args()

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found at {PDF_DIR}", file=sys.stderr)
        return 1

    if args.debug:
        # resolve filename
        if "/" in args.debug or "\\" in args.debug:
            target = Path(args.debug)
        else:
            target = PDF_DIR / args.debug
        if not target.exists():
            print(f"Debug target not found: {target}", file=sys.stderr)
            return 1
        # Build a full roster + seated map from all PDFs (for date-aware
        # fallback).
        all_pdfs = sorted(PDF_DIR.glob("*.pdf"))
        roster, seated_by_date = collect_member_roster_and_seated(all_pdfs)
        date, mid = pdf_meta_from_filename(target.name)
        present, absent = seated_roster_for_date(target.name, seated_by_date)
        votes, log = parse_pdf(
            target, date, mid, roster, debug=True,
            present_override=present, absent_override=absent,
        )
        for line in log:
            print("LOG:", line)
        return 0

    if args.limit:
        pdf_files = pdf_files[: args.limit]

    print(f"Scanning {len(pdf_files)} PDFs for roll-call roster ...")
    roster, seated_by_date = collect_member_roster_and_seated(pdf_files)
    print(f"Member roster ({len(roster)}): {roster}")

    all_votes: List[dict] = []
    all_logs: List[str] = []
    per_pdf_count: Counter = Counter()
    per_fmt_count: Counter = Counter()

    for i, p in enumerate(pdf_files, 1):
        date, mid = pdf_meta_from_filename(p.name)
        # Use this PDF's own present list, or borrow from neighbour if missing.
        present, absent = seated_roster_for_date(p.name, seated_by_date)
        try:
            votes, log = parse_pdf(
                p, date, mid, roster, debug=False,
                present_override=present, absent_override=absent,
            )
        except Exception as e:
            tb = traceback.format_exc()
            all_logs.append(f"[{p.name}] EXCEPTION: {e}\n{tb}")
            continue
        all_votes.extend(votes)
        all_logs.extend(log)
        per_pdf_count[p.name] = len(votes)
        for v in votes:
            per_fmt_count[v.get("__fmt", "?")] += 1
        if i % 10 == 0 or i == len(pdf_files):
            print(f"  [{i}/{len(pdf_files)}] {p.name}: {len(votes)} votes")

    # Write CSV
    # Column order:
    cols = [
        "meeting_date", "meeting_id", "pdf_file",
        "item_number", "item_title", "motion_summary",
        "outcome", "vote_count_for", "vote_count_against",
        "mover", "seconder",
    ] + roster + ["notes"]

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for v in all_votes:
            w.writerow(v)
    print(f"Wrote {len(all_votes)} votes to {OUT_CSV}")

    # Summary stats
    fully_resolved = 0
    any_unknown = 0
    for v in all_votes:
        unknowns = sum(1 for m in roster if v.get(m) == "Unknown")
        if unknowns == 0:
            fully_resolved += 1
        else:
            any_unknown += 1

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("OCEANSIDE CITY COUNCIL VOTE PARSE LOG\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total PDFs:         {len(pdf_files)}\n")
        f.write(f"Total votes parsed: {len(all_votes)}\n")
        f.write(f"Fully resolved:     {fully_resolved}\n")
        f.write(f"Rows with Unknown:  {any_unknown}\n")
        f.write("\nVotes by format:\n")
        for fmt, cnt in per_fmt_count.most_common():
            f.write(f"  {fmt}: {cnt}\n")
        f.write(f"\nMember roster: {roster}\n\n")
        f.write("\nPer-PDF vote counts:\n")
        for name in sorted(per_pdf_count):
            f.write(f"  {name}: {per_pdf_count[name]}\n")
        zero_pdfs = [n for n, c in per_pdf_count.items() if c == 0]
        if zero_pdfs:
            f.write("\nPDFs with 0 votes (suspicious, may need pattern work):\n")
            for n in zero_pdfs:
                f.write(f"  {n}\n")
        f.write("\n\nIssues / Warnings:\n")
        if not all_logs:
            f.write("  (none)\n")
        else:
            for line in all_logs:
                f.write(f"  {line}\n")
    print(f"Wrote log to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
