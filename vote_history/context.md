# Oceanside City Council Vote History (Dec 2022 – Apr 2026)

## What this is

A structured dataset of every recorded vote cast by every sitting Oceanside City
Council member (and Mayor) since [Eric Joyce was sworn in on Dec 14, 2022](https://www.ci.oceanside.ca.us/government/city-council/councilmember-eric-joyce).
Built from the official "Clerk's Action Minutes" PDFs.

- **94** City Council meetings enumerated (full + joint Council/HDB/CDC/OPFA sessions)
- **90** minutes PDFs downloaded (4 are upcoming meetings with no minutes yet)
- **82** PDFs had parseable motions (the other 8 are workshop/interview/closed-session-only agendas with no votes)
- **1,227** individual vote records in `votes.csv`
- **100%** of rows have fully-resolved individual member positions (no `Unknown`)

## File layout

| Path | Contents |
|---|---|
| [votes.csv](votes.csv) | **Source of truth.** 1 row = 1 recorded motion with outcome + per-member position columns. |
| [meetings.json](meetings.json) | Full Legistar catalog of City Council meetings with agenda/minutes/packet URLs. |
| [index.md](index.md) | Human-friendly entry point. |
| [by_member/](by_member/) | One markdown file per member: all their votes + a dissents/abstentions table. |
| [by_meeting/](by_meeting/) | One markdown file per meeting: every vote, one member per column. |
| [pdfs/](pdfs/) | Original minutes PDFs, named `YYYY-MM-DD_id-<legistar_id>.pdf`. |
| [scripts/](scripts/) | `enumerate_meetings.py` → `download_pdfs.py` → `parse_votes.py` → `build_views.py`. |
| [parse_log.txt](parse_log.txt) | Per-PDF vote counts + warnings for ambiguous rows. |

## votes.csv schema

```
meeting_date, meeting_id, pdf_file,
item_number, item_title, motion_summary,
outcome, vote_count_for, vote_count_against,
mover, seconder,
SANCHEZ, KEIM, JOYCE, ROBINSON, WEISS, FIGUEROA, RODRIGUEZ,
notes
```

Per-member cells: `Yes` | `No` | `Abstain` | `Absent` | `NotOnCouncil` | `Unknown`.

## Source notes

- **Legistar** ([oceanside.legistar.com](https://oceanside.legistar.com/)) is the
  live source. The Calendar's "all departments" view silently caps rows, so the
  enumerator filters by `Body = "City Council"` + one year at a time and paginates.
- **Records portal** ([records.ci.oceanside.ca.us](https://records.ci.oceanside.ca.us/gov/council/agenda.asp))
  holds the pre-Legistar PDFs — but Legistar has now backfilled everything from
  Dec 2022 onward, so we only use Legistar.
- PDFs come in two formats: pre-Oct 2024 "Action Minutes" (free-form `Motion: / Second: / Approved: N-M`)
  and Oct 2024+ "Clerk's Action Minutes" (structured `RESULT: / MOVER: / SECONDER: / Aye: / Nay:`).
  The parser handles both and the hybrid PDFs where old-style lines appear inside the new template.

## Regenerating

```bash
cd scripts
python enumerate_meetings.py   # → meetings.json
python download_pdfs.py         # → pdfs/*.pdf
python parse_votes.py           # → votes.csv + parse_log.txt
python build_views.py           # → by_member/, by_meeting/, index.md
```

## Known limitations

- A few "Approved: 5-0" orphan lines in the older PDFs were not attached to a
  preceding motion; those items are omitted from `votes.csv` rather than being
  guessed at. See `parse_log.txt` for the list.
- Closed-session items (`CONFERENCE WITH …`) are excluded from `votes.csv` —
  they're discussed privately and don't have recorded public votes.
- Roster is derived dynamically from each PDF's `Present:` line, so `NotOnCouncil`
  on any given row means "not in that meeting's roster" — verify against the
  PDF if you care about exact term boundaries (e.g., Keim's tenure, which ends
  mid-Dec 2024 when the new council is seated).
- One narrow special-case is hardcoded in the parser: the Dec 14, 2022 special
  meeting's first vote (certifying election results) is cast by the outgoing
  council, so Joyce — sworn in later the same day — is marked `NotOnCouncil`
  for that one row.
