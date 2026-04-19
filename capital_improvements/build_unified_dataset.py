"""Merge the three sources into a unified per-year CIP project view.

Sources:
1. GIS feature service (current + recent, no costs) — oceanside_cip_projects.json
2. FY25-26 CIP Book (5-year forward plan with costs) — fy2526_cip_projects.json
3. FY06-08 CIP Book (historical, OCR'd) — fy0608_cip_projects.json
4. Legistar matters (2020-2024, supplementary) — legistar_cip_matters.json

Output: unified_cip.json with a single list of observations, each tagged with source and fiscal year.
"""
import os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))

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


# Mode orientation: classify road/transport projects as AT vs auto-capacity vs
# auto-maintenance vs other. Auto-capacity = projects that add lanes or vehicle
# throughput (widening, new signals for cars, thoroughfare/arterial capacity,
# adaptive signal timing, roundabouts). Auto-maintenance = preserving the
# existing car-first network (overlay, slurry seal, pavement mgmt, bridge
# seismic retrofit, guardrails, radar feedback signs). AT has priority when
# a project matches both.
AUTO_CAPACITY_SINGLE = [
    'widening','widen','widens','widened',
    'thoroughfare','roundabout','roundabouts',
]
AUTO_CAPACITY_PHRASES = [
    'lane addition','additional lane','add lane','add lanes',
    'new signal','signal installation','signal installations',
    'signal modification','new traffic signal','new signals and',
    'adaptive signal','adaptive signal timing',
    'capacity expansion','capacity improvement','capacity increase',
    'intersection expansion','intersection improvement',
    'corridor design','corridor improvement',
    'freeway','overpass','grade separation',
    'median to',  # e.g., "Camino Real Median Mesa to Mission" = median-to-arterial
]
AUTO_MAINTENANCE_SINGLE = [
    'overlay','overlays','slurry','resurfac',  # catches resurface/resurfacing
    'guardrail','guardrails','repaving',
]
AUTO_MAINTENANCE_PHRASES = [
    'asphalt overlay','street overlay','pavement overlay',
    'road repairs','street restoration','street maintenance',
    'road maintenance','pavement management',
    'street monument preservation','monument preservation',
    'seismic retrofit','bridge retrofit','bridge resurface',
    'radar feedback','signal timing','traffic signal timing',
    'street reconstruction','road reconstruction',
    'alley improvement','median maintenance',
    'new signals and signal modifications',  # umbrella maintenance line
]
AUTO_MAINTENANCE_NAME_REGEX = re.compile(
    # "Street and Median Maintenance" / "Streets Maintenance" / etc.
    r'\bstreet(?:s)?(?:\s+(?:and|&)\s+\w+)?\s+maintenance\b',
    re.I,
)

AUTO_CAPACITY_RE = re.compile(r'\b(?:' + '|'.join(map(re.escape, AUTO_CAPACITY_SINGLE)) + r')\w*\b', re.I)
AUTO_MAINT_RE = re.compile(r'\b(?:' + '|'.join(map(re.escape, AUTO_MAINTENANCE_SINGLE)) + r')\w*\b', re.I)

def _has(text, rx, phrases):
    t = (text or '').lower()
    if rx.search(t): return True
    return any(p in t for p in phrases)

def mode_orientation(project_name, description='', category=''):
    """Return one of: active_transport, auto_capacity, auto_maintenance, other_infra.
    AT takes priority. Only transportation-flavored projects fall into the
    auto_* buckets — projects with category Parks/Municipal Buildings/Water/
    Sewer/Harbor/Drainage are bucketed as other_infra even if they mention
    'signal' or similar in passing."""
    blob = f'{project_name} {description}'
    if has_at(blob):
        return 'active_transport'
    # Only transportation-category projects can be auto_* classed
    transport_cats = {
        'TransNet Program','SB1 Program','Thoroughfare Program',
        'Thoroughfare/Signals Program','Measure X',
        None,'',  # FY06-08 book doesn't have explicit categories
    }
    # For FY06-08 (no category), allow auto_* if the name contains transport-y words
    transportation_hint = bool(re.search(
        r'\b(street|road|traffic|signal|boulevard|avenue|highway|intersection|thoroughfare|overlay|slurry|pavement|bridge|ramp|lane|asphalt|reconstruction)\b',
        blob, re.I,
    ))
    if category not in transport_cats and not transportation_hint:
        return 'other_infra'
    if _has(blob, AUTO_CAPACITY_RE, AUTO_CAPACITY_PHRASES):
        return 'auto_capacity'
    if _has(blob, AUTO_MAINT_RE, AUTO_MAINTENANCE_PHRASES):
        return 'auto_maintenance'
    if AUTO_MAINTENANCE_NAME_REGEX.search(blob):
        return 'auto_maintenance'
    return 'other_infra'


def load(path):
    if not os.path.exists(path): return None
    return json.load(open(path, encoding='utf-8'))


# Enterprise funds are excluded from the General CIP memo the City publishes
# (Water, Sewer, Harbor — plus selected grant-only projects). Use this to
# separate General-CIP analysis from enterprise-fund analysis.
ENTERPRISE_CATEGORIES = {
    'Water Program', 'Sewer Program', 'Harbor',
}

def classify_cip_class(category):
    if not category: return 'unknown'
    return 'enterprise' if category in ENTERPRISE_CATEGORIES else 'general'


def main():
    gis = load(os.path.join(HERE, 'oceanside_cip_projects.json'))
    fy2526 = load(os.path.join(HERE, 'fy2526_cip_projects.json'))
    fy0608 = load(os.path.join(HERE, 'fy0608_cip_projects.json'))
    legistar = load(os.path.join(HERE, 'legistar_cip_matters.json'))

    observations = []

    # --- GIS: no cost, but has schedule/status/location ---
    if gis:
        for p in gis.get('projects', []):
            # GIS feed only contains General Engineering CIP — Water Utilities
            # are in a separate feed that isn't part of this dataset.
            observations.append({
                'source': 'gis',
                'cip_class': 'general',
                'fiscal_year_window': f"{p.get('begin_year')}-{p.get('end_year')}" if p.get('begin_year') else None,
                'project_id': p.get('project_number'),
                'project_name': p.get('name'),
                'category': p.get('type'),
                'phase': p.get('current_phase'),
                'location': p.get('location'),
                'district': p.get('district'),
                'description': p.get('description'),
                'begin_year': p.get('begin_year'),
                'end_year': p.get('end_year'),
                'funding_sources': [p.get(f'fund_source_{i}') for i in range(1,7) if p.get(f'fund_source_{i}')],
                'cost_5yr_total': None,
                'annual_costs': {},
                'likely_active_transportation': p.get('likely_active_transportation'),
            })

    # --- FY25-26 CIP Book: 5-year forward plan with costs ---
    if fy2526:
        for p in fy2526.get('projects', []):
            annual = {}
            for fr in p.get('funding_by_source', []):
                for yr, key in [('2025-26','fy2025_26'),('2026-27','fy2026_27'),
                                ('2027-28','fy2027_28'),('2028-29','fy2028_29'),
                                ('2029-30','fy2029_30')]:
                    v = fr.get(key) or 0
                    annual[yr] = annual.get(yr, 0) + v
            observations.append({
                'source': 'fy2526_book',
                'cip_class': classify_cip_class(p.get('project_category')),
                'fiscal_year_window': '2025-2030',
                'project_id': p.get('project_number'),
                'project_name': p.get('project_name'),
                'category': p.get('project_category'),
                'phase': None,
                'location': p.get('project_location'),
                'district': p.get('council_district'),
                'description': p.get('description'),
                'status_narrative': p.get('status'),
                'begin_year': 2025,
                'end_year': 2030,
                'funding_sources': list({fr.get('funding_source') for fr in p.get('funding_by_source', []) if fr.get('funding_source')}),
                'cost_5yr_total': p.get('five_year_total'),
                'prior_year_project_cost': (p.get('funding_overview') or {}).get('Prior Year Project Cost'),
                'annual_costs': annual,
                'gis_project_number': p.get('gis_project_number'),
                'likely_active_transportation': p.get('likely_active_transportation'),
            })

    # --- FY06-08 CIP Book (OCR'd): 5-year plan for FY06-07 through FY10-11 ---
    if fy0608:
        for p in fy0608.get('projects', []):
            annual = {}
            for fr in p.get('funding_sources', []):
                for yr, key in [('2006-07','fy06_07'),('2007-08','fy07_08'),
                                ('2008-09','fy08_09'),('2009-10','fy09_10'),
                                ('2010-11','fy10_11')]:
                    v = fr.get(key) or 0
                    annual[yr] = annual.get(yr, 0) + v
            # FY06-08 book classification: infer enterprise vs general from
            # the management department (Water Utility / Sewer projects = enterprise).
            mgmt = (p.get('management_dept') or '').lower()
            src_labels = ' '.join((fr.get('source') or '').lower() for fr in p.get('funding_sources', []))
            blob = f'{mgmt} {src_labels} {(p.get("project_name") or "").lower()}'
            is_enterprise = any(k in blob for k in ('water fund','water utility','sewer','wwtp','outfall','harbor','lift station','desalter','reclaimed'))
            observations.append({
                'source': 'fy0608_book',
                'cip_class': 'enterprise' if is_enterprise else 'general',
                'fiscal_year_window': '2006-2011',
                'project_id': None,  # FY06-08 book has no ID
                'project_name': p.get('project_name'),
                'category': p.get('type_of_project'),
                'phase': None,
                'location': None,
                'district': None,
                'description': p.get('description'),
                'begin_year': 2006,
                'end_year': 2011,
                'management_dept': p.get('management_dept'),
                'funding_sources': [fr.get('source') for fr in p.get('funding_sources', [])],
                'cost_5yr_total': p.get('five_year_total_funding'),
                'annual_costs': annual,
                'operating_budget_impact': p.get('operating_budget_impact'),
                'likely_active_transportation': p.get('likely_active_transportation'),
            })

    # --- Legistar supplementary (2024 only, mostly grant appropriations) ---
    if legistar:
        for m in legistar.get('matters', []):
            dollars = m.get('dollars_in_title', [])
            title = m.get('title') or ''
            observations.append({
                'source': 'legistar_2024',
                'cip_class': 'unknown',
                'fiscal_year_window': '2024-25',
                'project_id': m.get('file_number'),
                'project_name': (title[:200]) if title else None,
                'description': title,
                'category': m.get('type'),
                'on_agenda': m.get('on_agenda'),
                'dollars_in_title': dollars,
                'likely_active_transportation': has_at(title),
            })

    # Re-evaluate AT flag + mode_orientation with unified heuristic
    for obs in observations:
        blob = ' '.join(str(obs.get(k) or '') for k in ('project_name','description','category','location'))
        obs['likely_active_transportation'] = has_at(blob)
        obs['at_keywords_matched'] = at_hits(blob)
        obs['mode_orientation'] = mode_orientation(
            obs.get('project_name') or '',
            obs.get('description') or '',
            obs.get('category') or '',
        )

    out = {
        'generated_utc': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),
        'observation_count': len(observations),
        'sources': {
            'gis': gis and gis.get('project_count'),
            'fy2526_book': fy2526 and fy2526.get('extracted_project_count'),
            'fy0608_book': fy0608 and fy0608.get('extracted_project_count'),
            'legistar_2024': legistar and legistar.get('matter_count'),
        },
        'fiscal_year_coverage': {
            'FY 2006-07 through FY 2010-11': 'fy0608_book (OCR)',
            'FY 2021-22 through FY 2025-26': 'gis (schedule/status only)',
            'FY 2025-26 through FY 2029-30': 'fy2526_book (per-project cost)',
            'FY 2024-25': 'legistar_2024 (supplementary grants + appropriations)',
        },
        'gap': 'FY 2011-12 through FY 2020-21: no per-project historical cost data available (operating budgets contain only narrative CIP sections; dedicated CIP Books from that era are not publicly posted or archived).',
        'observations': observations,
    }
    with open(os.path.join(HERE, 'unified_cip.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    # Print stats
    from collections import Counter
    by_src = Counter(o['source'] for o in observations)
    print(f'Unified observations: {len(observations)}')
    print(f'By source: {dict(by_src)}')
    print()

    def breakdown(obs_list, label):
        total = sum((o.get('cost_5yr_total') or 0) for o in obs_list)
        at = [o for o in obs_list if o.get('likely_active_transportation')]
        at_total = sum((o.get('cost_5yr_total') or 0) for o in at)
        pct = (at_total/total*100) if total else 0
        return f'{label:30s} n={len(obs_list):3d}  total=${total:>14,.0f}  AT n={len(at):2d}  AT $={at_total:>12,.0f} ({pct:4.1f}%)'

    # Per-source, per-cip_class breakdown
    print('=== Per source ===')
    for src in ['fy0608_book','gis','fy2526_book','legistar_2024']:
        obs = [o for o in observations if o['source']==src]
        print(breakdown(obs, src))
    print()
    print('=== CIP class (across ALL sources with cost data) ===')
    for cls in ['general','enterprise','unknown']:
        obs = [o for o in observations if o.get('cip_class')==cls]
        print(breakdown(obs, cls))
    print()
    print('=== General CIP only, per source ===')
    for src in ['fy0608_book','fy2526_book']:
        obs = [o for o in observations if o['source']==src and o.get('cip_class')=='general']
        print(breakdown(obs, src))
    print()
    print('=== Mode orientation — General CIP, per era ===')
    for src, era in [('fy0608_book','FY06-10'),('fy2526_book','FY25-30')]:
        era_obs = [o for o in observations if o['source']==src and o.get('cip_class')=='general']
        era_total = sum((o.get('cost_5yr_total') or 0) for o in era_obs)
        print(f'\n{era}  total = ${era_total:,.0f}')
        for mode in ['active_transport','auto_capacity','auto_maintenance','other_infra']:
            m_obs = [o for o in era_obs if o.get('mode_orientation')==mode]
            m_total = sum((o.get('cost_5yr_total') or 0) for o in m_obs)
            pct = (m_total/era_total*100) if era_total else 0
            print(f'  {mode:20s}  n={len(m_obs):3d}  ${m_total:>12,.0f} ({pct:5.1f}%)')


if __name__ == '__main__':
    main()
