"""Extract FY 2025-26 CIP Budget Book project detail into JSON + CSV.
Re-runnable after raw_pdfs/FY2526_CIP_budget.pdf is downloaded."""
from pypdf import PdfReader
from difflib import SequenceMatcher
import re, json, csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'raw_pdfs', 'FY2526_CIP_budget.pdf')

AT_SINGLE = [
    'bike','bicycle','bicyclist','bicycles','pedestrian','pedestrians',
    'sidewalk','sidewalks','crosswalk','crosswalks','trail','trails',
    'greenway','bikeway','bikeways','rrfb','srts','bike lane',
]
AT_PHRASES = [
    'buffered lane','hawk signal','complete streets','safe routes',
    'active transportation','ada ramp','pedestrian bridge',
    'pedestrian crossing','traffic calming','speed control',
    'school zone','rail trail','bike path',
]
AT_RE = re.compile(
    r'\b(?:' + '|'.join(map(re.escape, AT_SINGLE)) + r')\b',
    re.I,
)

def parse_money(s):
    if s is None: return 0
    if isinstance(s,(int,float)): return s
    s = str(s).strip().replace('$','').replace(',','').replace('(','-').replace(')','')
    if s in ('','-'): return 0
    try: return float(s)
    except: return None

def has_at(text):
    t = (text or '').lower()
    if AT_RE.search(t): return True
    return any(k in t for k in AT_PHRASES)

def at_hits(text):
    t = (text or '').lower()
    hits = set()
    for m in AT_RE.finditer(t): hits.add(m.group(0).lower())
    for k in AT_PHRASES:
        if k in t: hits.add(k)
    return sorted(hits)

def extract_project(pages_text):
    lines = pages_text.split('\n')
    lines_stripped = [l.strip() for l in lines]
    try:
        idx = lines_stripped.index('PROJECT NUMBER')
    except ValueError:
        return None
    title_lines = []
    # The same round bullet glyph extracts as different codepoints across pages
    # (observed: U+00A8, U+00FD, U+2022, U+FFFD). Treat any single-char line as a bullet.
    for j in range(idx-1, -1, -1):
        s = lines_stripped[j]
        if len(s) == 1:
            break
        if s:
            title_lines.append(s)
    name = ' '.join(reversed(title_lines)).strip()
    name = re.sub(r'\s+', ' ', name)

    def after_label(label):
        try:
            i = lines_stripped.index(label)
            return lines_stripped[i+1] if i+1 < len(lines_stripped) else None
        except ValueError:
            return None

    def multiline_after(label, stop_labels):
        try:
            i = lines_stripped.index(label)
        except ValueError:
            return None
        out = []
        for j in range(i+1, len(lines_stripped)):
            if lines_stripped[j] in stop_labels: break
            out.append(lines_stripped[j])
        return ' '.join(x for x in out if x).strip() or None

    proj_num = after_label('PROJECT NUMBER')
    district = after_label('COUNCIL DISTRICT')
    category = after_label('PROJECT CATEGORY')
    location = after_label('PROJECT LOCATION')
    description = multiline_after('PROJECT DESCRIPTION', {'PROJECT STATUS','OPERATING BUDGET IMPACT','PROJECT FUNDING OVERVIEW'})
    status = multiline_after('PROJECT STATUS', {'OPERATING BUDGET IMPACT','PROJECT FUNDING OVERVIEW'})
    op_budget_impact = multiline_after('OPERATING BUDGET IMPACT', {'PROJECT FUNDING OVERVIEW'})

    funding_overview = {}
    try:
        i = lines_stripped.index('PROJECT FUNDING OVERVIEW')
        labels = ['Prior Year Project Cost','Unused Funds','Five Year Plan','Remaining Needed']
        vals = []
        for j in range(i+1, len(lines_stripped)):
            s = lines_stripped[j]
            if s in labels: continue
            if s.startswith('1-YEAR'): break
            if s and (s[0] in '$-' or s[0].isdigit()):
                vals.append(parse_money(s))
            if len(vals) >= 4: break
        for k,v in zip(labels, vals):
            funding_overview[k] = v
    except ValueError:
        pass

    fund_rows = []
    try:
        i = lines_stripped.index('1-YEAR BUDGET AND 5-YEAR PLAN')
        j = i + 1
        header_labels = {'Fund','Funding Source','2025/26','2026/27','2027/28','2028/29','2029/30','TOTAL'}
        while j < len(lines_stripped) and lines_stripped[j] in header_labels:
            j += 1
        row = []
        while j < len(lines_stripped):
            s = lines_stripped[j]
            if not s:
                j += 1; continue
            if s.startswith('Capital Improvement Program') or re.match(r'^[A-Za-z][A-Za-z ]+Program-', s):
                break
            row.append(s)
            if len(row) == 8:
                code, src, *vals = row
                fund_rows.append({
                    'fund_code': code,
                    'funding_source': src,
                    'fy2025_26': parse_money(vals[0]),
                    'fy2026_27': parse_money(vals[1]),
                    'fy2027_28': parse_money(vals[2]),
                    'fy2028_29': parse_money(vals[3]),
                    'fy2029_30': parse_money(vals[4]),
                    'total_5yr': parse_money(vals[5]),
                })
                row = []
            j += 1
    except ValueError:
        pass

    return {
        'project_name': name,
        'project_number': proj_num,
        'council_district': district,
        'project_category': category,
        'project_location': location,
        'description': description,
        'status': status,
        'operating_budget_impact': op_budget_impact,
        'funding_overview': funding_overview,
        'funding_by_source': fund_rows,
        'five_year_total': sum((fr.get('total_5yr') or 0) for fr in fund_rows) if fund_rows else None,
    }

def main():
    r = PdfReader(SRC)
    projects = []
    page_texts = [(i, r.pages[i].extract_text() or '') for i in range(len(r.pages))]
    i = 0
    while i < len(page_texts):
        idx, text = page_texts[i]
        if 'PROJECT NUMBER' not in text:
            i += 1; continue
        combined = text
        j = i + 1
        while j < len(page_texts) and 'PROJECT NUMBER' not in page_texts[j][1]:
            combined += '\n' + page_texts[j][1]; j += 1
        p = extract_project(combined)
        if p:
            p['pdf_page'] = idx + 1
            projects.append(p)
        i = j

    gis_path = os.path.join(HERE, 'oceanside_cip_projects.json')
    gis = json.load(open(gis_path, encoding='utf-8'))['projects'] if os.path.exists(gis_path) else []

    def norm(s):
        s = (s or '').lower()
        s = re.sub(r'[^a-z0-9 ]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def best_match(name):
        nname = norm(name)
        if not nname: return (None, 0)
        best = (None, 0)
        for c in gis:
            cname = norm(c.get('name') or '')
            if not cname: continue
            rr = SequenceMatcher(None, nname, cname).ratio()
            if rr > best[1]:
                best = (c, rr)
        return best

    for p in projects:
        blob = ' '.join(str(p.get(k) or '') for k in ('project_name','description','status','project_location'))
        p['likely_active_transportation'] = has_at(blob)
        p['at_keywords_matched'] = at_hits(blob)
        m, s = best_match(p.get('project_name'))
        p['gis_project_number'] = m.get('project_number') if m and s >= 0.75 else None
        p['gis_match_score'] = round(s, 3) if m else 0

    # Re-tag GIS projects with refined heuristic too
    for p in gis:
        blob = ' '.join(str(p.get(k) or '') for k in ('name','description','location','type'))
        p['likely_active_transportation'] = has_at(blob)
        p['at_keywords_matched'] = at_hits(blob)

    with open(os.path.join(HERE, 'fy2526_cip_projects.json'), 'w', encoding='utf-8') as fp:
        json.dump({
            'source': 'City of Oceanside — FY 2025-26 Five Year Capital Improvement Program Budget',
            'source_pdf': 'raw_pdfs/FY2526_CIP_budget.pdf',
            'source_url': 'https://www.ci.oceanside.ca.us/home/showpublisheddocument/16819/638876730137700000',
            'publish_date': '2025-04-24',
            'extracted_project_count': len(projects),
            'coverage': 'Individual project detail for FY2025-26 plus 4-year projection through FY2029-30. Includes enterprise funds (Water, Sewer, Harbor).',
            'projects': projects,
        }, fp, indent=2, ensure_ascii=False)

    if gis:
        gis_json = json.load(open(gis_path, encoding='utf-8'))
        gis_json['projects'] = gis
        json.dump(gis_json, open(gis_path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

    csv_rows = []
    for p in projects:
        base = {
            'project_name': p.get('project_name'),
            'project_number': p.get('project_number'),
            'council_district': p.get('council_district'),
            'project_category': p.get('project_category'),
            'project_location': p.get('project_location'),
            'likely_active_transportation': p.get('likely_active_transportation'),
            'at_keywords_matched': ';'.join(p.get('at_keywords_matched') or []),
            'prior_year_project_cost': (p.get('funding_overview') or {}).get('Prior Year Project Cost'),
            'unused_funds': (p.get('funding_overview') or {}).get('Unused Funds'),
            'five_year_plan_total': (p.get('funding_overview') or {}).get('Five Year Plan'),
            'remaining_needed': (p.get('funding_overview') or {}).get('Remaining Needed'),
            'five_year_total_sum_of_rows': p.get('five_year_total'),
            'gis_project_number': p.get('gis_project_number'),
        }
        if not p.get('funding_by_source'):
            csv_rows.append({**base, 'fund_code': None, 'funding_source': None,
                             'fy2025_26': None, 'fy2026_27': None, 'fy2027_28': None,
                             'fy2028_29': None, 'fy2029_30': None, 'row_5yr_total': None})
        else:
            for r2 in p['funding_by_source']:
                csv_rows.append({**base,
                    'fund_code': r2.get('fund_code'),
                    'funding_source': r2.get('funding_source'),
                    'fy2025_26': r2.get('fy2025_26'),
                    'fy2026_27': r2.get('fy2026_27'),
                    'fy2027_28': r2.get('fy2027_28'),
                    'fy2028_29': r2.get('fy2028_29'),
                    'fy2029_30': r2.get('fy2029_30'),
                    'row_5yr_total': r2.get('total_5yr'),
                })

    with open(os.path.join(HERE, 'fy2526_cip_funding_rows.csv'), 'w', encoding='utf-8', newline='') as fp:
        w = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()))
        w.writeheader(); w.writerows(csv_rows)

    at = [p for p in projects if p['likely_active_transportation']]
    at_spend = sum((p.get('five_year_total') or 0) for p in at)
    total = sum((p.get('five_year_total') or 0) for p in projects)
    print(f'FY25-26 book: {len(projects)} projects, ${total:,.0f} 5-year plan')
    print(f'Active-transportation: {len(at)} projects, ${at_spend:,.0f} ({at_spend/total*100:.1f}%)')
    print(f'GIS crosswalk matches: {sum(1 for p in projects if p.get("gis_project_number"))}/{len(projects)}')
    print()
    print('Active-transportation projects, by 5yr spend:')
    for p in sorted(at, key=lambda x: -(x.get('five_year_total') or 0)):
        print(f"  ${(p.get('five_year_total') or 0):>11,.0f}  [{p.get('project_category') or '-':<22}]  {p['project_name']}")

if __name__ == '__main__':
    main()
