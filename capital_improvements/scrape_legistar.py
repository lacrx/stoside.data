"""Oceanside Legistar harvest v2: multiple targeted search terms per year.

Legistar caps results at 100/search, so run several CIP-related queries per year."""
import os, re, json, time
from urllib.parse import urlencode
import urllib.request as ur
from http.cookiejar import CookieJar, Cookie

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'raw_pdfs', 'legistar_fy15_fy24')
os.makedirs(OUT, exist_ok=True)

BASE = 'https://oceanside.legistar.com/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

QUERIES = [
    'capital improvement',
    'CIP budget',
    'appropriating',
    'SB1',
    'SB 1 project',
    'TransNet',
    'bicycle',
    'pedestrian',
    'bike',
    'sidewalk',
    'safe routes',
    'pavement',
    'traffic signal',
    'trail',
    'crosswalk',
    'Measure X spending',
    'traffic calming',
]


def make_opener():
    cj = CookieJar()
    o = ur.build_opener(ur.HTTPCookieProcessor(cj))
    o.addheaders = [
        ('User-Agent', UA),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        ('Accept-Language', 'en-US,en;q=0.9'),
        ('Referer', BASE + 'Legislation.aspx'),
    ]
    return o, cj


def viewstate_fields(html):
    fields = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html):
        fields[m.group(1)] = m.group(2)
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*value="([^"]*)"[^>]*name="([^"]+)"', html):
        fields.setdefault(m.group(2), m.group(1))
    return fields


def search(opener, cj, year, query):
    cj.clear()
    c = Cookie(0, 'Setting-957-Legislation Year', year, None, False,
               'oceanside.legistar.com', True, False, '/', True, True, None, False, None, None,
               {'HttpOnly': None}, False)
    cj.set_cookie(c)
    html = opener.open(BASE + 'Legislation.aspx', timeout=60).read().decode('utf-8', 'replace')
    f = viewstate_fields(html)
    data = [
        ('__VIEWSTATE', f.get('__VIEWSTATE', '')),
        ('__VIEWSTATEGENERATOR', f.get('__VIEWSTATEGENERATOR', '')),
        ('__EVENTVALIDATION', f.get('__EVENTVALIDATION', '')),
        ('ctl00$ContentPlaceHolder1$txtSearch', query),
        ('ctl00$ContentPlaceHolder1$lstYears', year),
        ('ctl00$ContentPlaceHolder1$lstTypeBasic', 'All'),
        ('ctl00$ContentPlaceHolder1$chkText', 'on'),
        ('ctl00$ContentPlaceHolder1$btnSearch', 'Search'),
    ]
    req = ur.Request(BASE + 'Legislation.aspx', data=urlencode(data).encode())
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Referer', BASE + 'Legislation.aspx')
    return opener.open(req, timeout=120).read().decode('utf-8', 'replace')


def parse_rows(html):
    rows = []
    seen = set()
    for tr in re.finditer(r'<tr[^>]*id="[^"]*gridMain_ctl00__\d+"[^>]*>(.*?)</tr>', html, re.S):
        h = tr.group(1)
        fm = re.search(r'LegislationDetail\.aspx\?ID=(\d+)&amp;GUID=([A-F0-9-]+)[^"]*"[^>]*>([^<]+)</a>', h)
        if not fm: continue
        mid, guid, fn = fm.group(1), fm.group(2), fm.group(3).strip()
        if mid in seen: continue
        seen.add(mid)
        tds = re.findall(r'<td[^>]*>(.*?)</td>', h, re.S)
        def clean(x):
            x = re.sub(r'<[^>]+>', ' ', x or '')
            x = x.replace('&nbsp;', ' ').replace('&amp;', '&')
            return re.sub(r'\s+', ' ', x).strip()
        cells = [clean(td) for td in tds]
        date = None
        for c in cells:
            dm = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})', c)
            if dm: date = dm.group(1); break
        candidates = [c for c in cells if c and c != fn and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}', c)]
        title = max(candidates, key=len, default='') if candidates else ''
        rows.append({'id': mid, 'guid': guid, 'file_number': fn,
                     'intro_date': date, 'title_snippet': title[:500]})
    return rows


def fetch_detail(opener, mid, guid):
    url = f'{BASE}LegislationDetail.aspx?ID={mid}&GUID={guid}&FullText=1'
    html = opener.open(url, timeout=60).read().decode('utf-8', 'replace')
    def sp(id_):
        m = re.search(rf'id="ctl00_ContentPlaceHolder1_{id_}"[^>]*>(.*?)</span>', html, re.S)
        if not m: return None
        t = re.sub(r'<[^>]+>', ' ', m.group(1))
        t = t.replace('&nbsp;', ' ').replace('&amp;', '&')
        return re.sub(r'\s+', ' ', t).strip() or None
    atts = []
    for m in re.finditer(r'View\.ashx\?M=F&amp;ID=(\d+)&amp;GUID=([A-F0-9-]+)[^"]*"[^>]*>([^<]+)</a>', html):
        atts.append({'file_id': m.group(1), 'guid': m.group(2), 'label': m.group(3).strip()})
    return {
        'id': mid, 'guid': guid, 'detail_url': url,
        'title': sp('lblTitle2'),
        'name': sp('lblName2'),
        'intro_date': sp('lblIntroDate2'),
        'final_date': sp('hypFinalDate') or sp('lblFinalDate2'),
        'file_created': sp('lblFileCreated2'),
        'on_agenda': sp('lblOnAgenda2'),
        'matter_type': sp('lblType2'),
        'attachments': atts,
    }


def is_cip(m):
    blob = ' '.join(str(v or '') for v in [
        m.get('title'), m.get('name'), m.get('title_snippet'),
    ]).lower()
    if not blob: return False
    TERMS = [
        'capital improvement', 'cip ', ' cip', 'cip-', ' cip,',
        'sb1 project', 'sb-1 project', 'sb 1 project', 'senate bill 1',
        'appropriat', 'bike', 'bicycle', 'pedestrian', 'sidewalk',
        'safe routes', 'transnet', 'measure x', 'pavement management',
        'complete streets', 'traffic calming', 'trail ',
        'crosswalk', 'ada ramp', 'rail trail', 'bikeway',
    ]
    return any(k in blob for k in TERMS)


def download(opener, url, path):
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        return 'cached'
    try:
        r = opener.open(url, timeout=180)
        data = r.read()
    except Exception as e:
        return f'error:{e}'
    with open(path, 'wb') as f:
        f.write(data)
    return f'ok {len(data)}'


def main():
    opener, cj = make_opener()
    all_matters = {}  # id -> row dict

    for year in [str(y) for y in range(2015, 2025)]:
        for q in QUERIES:
            try:
                html = search(opener, cj, year, q)
            except Exception as e:
                print(f'  year={year} q={q!r}: search error {e}')
                time.sleep(3); continue
            rows = parse_rows(html)
            new = 0
            for r in rows:
                if r['id'] not in all_matters:
                    r['search_year'] = year
                    r['found_by_query'] = q
                    all_matters[r['id']] = r
                    new += 1
            print(f'  year={year} q={q!r}: {len(rows)} rows, {new} new (total {len(all_matters)})', flush=True)
            time.sleep(0.5)

    # Fetch detail for all unique matters
    print(f'\nTotal unique matters: {len(all_matters)}')
    print('Fetching detail pages...')
    details = []
    items = list(all_matters.values())
    for i, m in enumerate(items, 1):
        try:
            d = fetch_detail(opener, m['id'], m['guid'])
        except Exception as e:
            print(f'  [{i}/{len(items)}] {m["id"]}: detail error {e}'); continue
        d['search_year'] = m.get('search_year')
        d['found_by_query'] = m.get('found_by_query')
        d['row_file_number'] = m.get('file_number')
        d['row_title_snippet'] = m.get('title_snippet')
        details.append(d)
        if i % 20 == 0:
            print(f'  [{i}/{len(items)}] details fetched', flush=True)
        time.sleep(0.3)

    # Final CIP filter on complete metadata
    final_cip = [d for d in details if is_cip(d)]
    print(f'\nFinal CIP matter count: {len(final_cip)}')

    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'fetched_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'year_range': '2015-2024',
            'all_matters_seen': len(details),
            'cip_matters': len(final_cip),
            'queries_per_year': QUERIES,
            'matters': final_cip,
        }, f, indent=2, ensure_ascii=False)
    print(f'Wrote index.json with {len(final_cip)} matters')

    # Download all attachments
    print('\nDownloading attachments...')
    err_count = 0
    for i, m in enumerate(final_cip, 1):
        for a in m.get('attachments', []):
            url = f"{BASE}View.ashx?M=F&ID={a['file_id']}&GUID={a['guid']}"
            path = os.path.join(OUT, f"matter_{m['id']}_file_{a['file_id']}.pdf")
            s = download(opener, url, path)
            if s.startswith('error'):
                err_count += 1
                if err_count < 5:
                    print(f'  [{i}] matter {m["id"]} file {a["file_id"]}: {s}')
            time.sleep(0.2)
        if i % 25 == 0:
            print(f'  attach progress: {i}/{len(final_cip)}', flush=True)
    print(f'DONE. errors={err_count}')


if __name__ == '__main__':
    main()
