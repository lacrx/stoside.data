"""
Enumerate Oceanside Legistar City Council meetings by year,
using Body=City Council + Year filters with pagination.
"""
import json
import re
from pathlib import Path
import requests

BASE = "https://oceanside.legistar.com"
CAL = f"{BASE}/Calendar.aspx"
HERE = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"}


def tokens(html):
    out = {}
    for n in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        m = re.search(rf'id="{n}"[^>]*value="([^"]*)"', html)
        if m:
            out[n] = m.group(1)
    return out


def form_base(html):
    t = tokens(html)
    return {
        "__VIEWSTATE": t.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": t.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": t.get("__EVENTVALIDATION", ""),
    }


def client_state(text):
    return json.dumps({
        "logEntries": [], "value": text, "text": text,
        "enabled": True, "checkedIndices": [], "checkedItemsTextOverflows": False,
    })


def post_set_body(session, html, body_text):
    data = form_base(html)
    data.update({
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lstBodies",
        "__EVENTARGUMENT": "",
        "ctl00$ContentPlaceHolder1$lstBodies": body_text,
        "ctl00_ContentPlaceHolder1_lstBodies_ClientState": client_state(body_text),
    })
    r = session.post(CAL, data=data, timeout=60)
    r.raise_for_status()
    return r.text


def post_set_year(session, html, year, body_text):
    data = form_base(html)
    data.update({
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lstYears",
        "__EVENTARGUMENT": "",
        "ctl00$ContentPlaceHolder1$lstYears": year,
        "ctl00_ContentPlaceHolder1_lstYears_ClientState": client_state(year),
        "ctl00$ContentPlaceHolder1$lstBodies": body_text,
        "ctl00_ContentPlaceHolder1_lstBodies_ClientState": client_state(body_text),
    })
    r = session.post(CAL, data=data, timeout=60)
    r.raise_for_status()
    return r.text


def post_page(session, html, ctl, year, body_text):
    data = form_base(html)
    data.update({
        "__EVENTTARGET": ctl,
        "__EVENTARGUMENT": "",
        "ctl00$ContentPlaceHolder1$lstYears": year,
        "ctl00_ContentPlaceHolder1_lstYears_ClientState": client_state(year),
        "ctl00$ContentPlaceHolder1$lstBodies": body_text,
        "ctl00_ContentPlaceHolder1_lstBodies_ClientState": client_state(body_text),
    })
    r = session.post(CAL, data=data, timeout=60)
    r.raise_for_status()
    return r.text


def extract_rows(html, grid="gridCalendar"):
    row_ids = re.findall(rf'id="ctl00_ContentPlaceHolder1_{grid}_ctl00__(\d+)"', html)
    out = []
    for rid in row_ids:
        pat = rf'<tr[^>]*id="ctl00_ContentPlaceHolder1_{grid}_ctl00__{rid}"[^>]*>(.*?)</tr>'
        m = re.search(pat, html, re.S)
        if m:
            out.append(m.group(1))
    return out


def parse_row(row):
    body_m = re.search(r'hypBody[^>]*>([^<]+)</a>', row)
    body = body_m.group(1).strip() if body_m else None

    date_m = re.search(r'<td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{4})\s*</td>', row)
    date = date_m.group(1) if date_m else None

    idg = re.search(
        r'(?:MeetingDetail\.aspx|View\.ashx)\?(?:M=[ACIM]P?&amp;)?ID=(\d+)&amp;GUID=([0-9A-F\-]+)',
        row
    )
    if not idg:
        return None
    mid, guid = idg.group(1), idg.group(2)

    time_m = re.search(r'lblTime[^>]*>([^<]+)</span>', row)
    time_s = time_m.group(1).strip() if time_m else None

    def has(M):
        return bool(re.search(rf'View\.ashx\?M={M}&amp;ID={mid}&amp;GUID={guid}', row))

    return {
        "meeting_id": mid,
        "guid": guid,
        "date": date,
        "body": body,
        "time": time_s,
        "detail_url": f"{BASE}/MeetingDetail.aspx?ID={mid}&GUID={guid}",
        "agenda_url": f"{BASE}/View.ashx?M=A&ID={mid}&GUID={guid}" if has("A") else None,
        "minutes_url": f"{BASE}/View.ashx?M=M&ID={mid}&GUID={guid}" if has("M") else None,
        "agenda_packet_url": f"{BASE}/View.ashx?M=AP&ID={mid}&GUID={guid}" if has("AP") else None,
    }


def page_links(html):
    pat = re.compile(
        r"NavigateToPage\(&#39;ctl00_ContentPlaceHolder1_gridCalendar_ctl00&#39;,\s*&#39;(\d+)&#39;\)[^<]*?"
        r"href=\"javascript:__doPostBack\(&#39;([^&]+)&#39;",
        re.S
    )
    found = {}
    for m in pat.finditer(html):
        found.setdefault(int(m.group(1)), m.group(2))
    return sorted(found.items())


def fetch_body_year(session, html, body, year):
    """Return (new_html, list_of_meeting_dicts) for Body+Year filter."""
    # set body first
    html = post_set_body(session, html, body)
    # then set year
    html = post_set_year(session, html, year, body)

    all_rows = extract_rows(html, "gridCalendar") + extract_rows(html, "gridUpcomingMeetings")
    links = page_links(html)
    max_page = max((p for p, _ in links), default=1)

    for pn in range(2, max_page + 1):
        ctl = dict(page_links(html)).get(pn)
        if not ctl:
            break
        html = post_page(session, html, ctl, year, body)
        all_rows += extract_rows(html, "gridCalendar")

    meetings = []
    for r in all_rows:
        p = parse_row(r)
        if p:
            meetings.append(p)
    return html, meetings


def main():
    session = requests.Session()
    session.headers.update(UA)
    r = session.get(CAL, timeout=30)
    html = r.text

    all_m = {}
    for year in ["2022", "2023", "2024", "2025", "2026"]:
        # Re-fetch fresh state to avoid cached filter conflicts
        r = session.get(CAL, timeout=30)
        html = r.text
        html, meetings = fetch_body_year(session, html, "City Council", year)
        print(f"{year}: {len(meetings)} City Council rows", flush=True)
        for m in meetings:
            all_m[m["meeting_id"]] = m

    final = sorted(all_m.values(), key=lambda m: m["date"] or "9999")
    out = HERE.parent / "meetings.json"
    out.write_text(json.dumps(final, indent=2))

    from datetime import datetime
    cutoff = datetime(2022, 12, 14)
    in_range = [m for m in final
                if m["date"] and datetime.strptime(m["date"], "%m/%d/%Y") >= cutoff]
    print(f"\nTotal City Council meetings: {len(final)}")
    print(f"On/after 2022-12-14: {len(in_range)}")
    print(f"  with minutes PDF: {sum(1 for m in in_range if m['minutes_url'])}")

    from collections import Counter
    yrs = Counter(m["date"].split("/")[-1] for m in in_range)
    for y, c in sorted(yrs.items()):
        print(f"  {y}: {c} council meetings")


if __name__ == "__main__":
    main()
