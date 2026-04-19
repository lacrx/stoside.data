"""OCR and extract project data from the FY 2006-08 Oceanside CIP Book PDF (scanned)."""
import os, sys, json, re, time
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

import fitz  # pymupdf
import easyocr
from PIL import Image
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, 'raw_pdfs', 'FY0608_CIP_section.pdf')
PAGE_DIR = os.path.join(HERE, 'raw_pdfs', 'FY0608_pages')
OCR_DIR = os.path.join(HERE, 'raw_pdfs', 'FY0608_ocr')
os.makedirs(PAGE_DIR, exist_ok=True)
os.makedirs(OCR_DIR, exist_ok=True)


def render_pages():
    doc = fitz.open(PDF)
    print(f'rendering {len(doc)} pages...')
    for i, page in enumerate(doc):
        png_path = os.path.join(PAGE_DIR, f'p{i+1:03d}.png')
        if os.path.exists(png_path):
            continue
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(png_path)
        if (i+1) % 10 == 0:
            print(f'  rendered {i+1}/{len(doc)}', flush=True)
    print('done rendering')


def ocr_all():
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    print('reader ready')
    pages = sorted(f for f in os.listdir(PAGE_DIR) if f.endswith('.png'))
    for i, fn in enumerate(pages, 1):
        out_path = os.path.join(OCR_DIR, fn.replace('.png', '.json'))
        if os.path.exists(out_path):
            continue
        png_path = os.path.join(PAGE_DIR, fn)
        t0 = time.time()
        try:
            lines = reader.readtext(png_path, detail=0, paragraph=False)
        except Exception as e:
            print(f'  {fn}: OCR error {e}')
            continue
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'page': int(fn[1:4]), 'lines': lines}, f, ensure_ascii=False)
        if i % 5 == 0:
            print(f'  ocr {i}/{len(pages)}, last page {time.time()-t0:.1f}s', flush=True)
    print('OCR complete')


def parse_project_pages():
    """Parse each page's OCR output. Project pages have 'Project Description:' marker."""
    pages = sorted(f for f in os.listdir(OCR_DIR) if f.endswith('.json'))
    projects = []
    for fn in pages:
        data = json.load(open(os.path.join(OCR_DIR, fn), encoding='utf-8'))
        lines = data['lines']
        lines_clean = [l.strip() for l in lines]
        text = '\n'.join(lines_clean)
        if 'Project Description' not in text:
            continue
        p = extract_one(lines_clean, data['page'])
        if p:
            projects.append(p)
    return projects


def clean_ocr_number(s):
    """Normalize an OCR'd dollar-amount token. Returns cleaned string or None."""
    if s is None: return None
    s = str(s).strip()
    # Strip leading currency-ish chars (S, $, space)
    s = re.sub(r'^[\$Ss]\s*', '', s)
    # Apply letter→digit substitutions FIRST, before stripping trailing junk,
    # so tokens like "500,00o" become "500,000" not "500,00".
    for a, b in [('O','0'),('o','0'),('l','1'),('I','1'),('|','1')]:
        s = s.replace(a, b)
    # Strip trailing stray chars that OCR sometimes adds (spaces, underscores, dashes)
    s = re.sub(r'[^\d,\.\-]+$', '', s)
    # Oceanside PDFs use commas as thousands separators. OCR occasionally reads
    # a thousands comma as a period (e.g., "2.200,000" for "2,200,000"). If the
    # string looks like two mismatched separators, treat "." as a thousands sep.
    if re.match(r'^\d{1,3}\.\d{3},\d{3}$', s):
        s = s.replace('.', '').replace(',', '')
    else:
        s = s.replace(',', '').replace(' ', '')
    # OCR sometimes appends a stray digit (not 0) to a round value
    # e.g. "2,500,0001" → "25000001". Only strip if the appended digit is NON-zero.
    if len(s) >= 8 and re.match(r'^\d+000[1-9]$', s):
        trunc = s[:-1]
        if re.match(r'^\d+000+$', trunc):
            s = trunc
    return s or None


def parse_money(s):
    cleaned = clean_ocr_number(s)
    if not cleaned or cleaned == '-': return 0
    try: return float(cleaned)
    except: return None


NUMERIC_PAT = re.compile(r'^[\$Ss]?\s*-?\d[\d,\.]*[\dOoIl|]*\s*$')


def is_numeric_line(s):
    """Lenient numeric detection that tolerates common OCR errors."""
    s = s.strip()
    if not s: return False
    t = re.sub(r'^[\$Ss]\s*', '', s)
    if t in ('-','','0'): return True
    # Strip trailing OCR junk (underscore, stray alpha, etc.) for classification
    t_clean = re.sub(r'[_\s\-]+$', '', t)
    if not t_clean: return False
    digit_chars = sum(1 for c in t_clean if c in '0123456789,.OoIl|')
    if digit_chars < 2: return False
    # Require the leading char to be digit-like (not a letter)
    if t_clean[0] not in '0123456789.,-$':
        return False
    non_digit = sum(1 for c in t_clean if c not in '0123456789,.OoIl| -')
    return non_digit <= 1 and digit_chars >= len(t_clean) - 1


def extract_one(lines, page_num):
    """Extract a single project's data from OCR'd lines."""
    # Find indexes
    def idx(pattern, default=None):
        for i, l in enumerate(lines):
            if re.search(pattern, l, re.I):
                return i
        return default

    # Tolerant of OCR noise: '_' in place of spaces, stray punctuation
    i_desc = idx(r'^Project[^A-Za-z]{0,4}Description')
    i_mgmt = idx(r'^Project[^A-Za-z]{0,4}Management')
    i_fund_hdr = idx(r'Funding[^A-Za-z]{0,4}Source')
    i_cost_hdr = idx(r'^Project[^A-Za-z]{0,4}Cost\b')
    i_type = idx(r'^Type of Project')
    i_impact = idx(r'Impact on Operating')

    # Title is the first prominent line at the top of the page (above Project Description).
    # Usually 1-3 lines.
    title_lines = []
    if i_desc is not None:
        for j in range(0, i_desc):
            l = lines[j].strip()
            if not l: continue
            # Skip page numbers or solitary digits
            if re.fullmatch(r'\d+', l): continue
            title_lines.append(l)
    title = ' '.join(title_lines).strip()

    # Description: between "Project Description:" and "Project Management"
    description = ''
    if i_desc is not None and i_mgmt is not None and i_mgmt > i_desc:
        desc_lines = []
        for l in lines[i_desc+1:i_mgmt]:
            l = l.strip()
            if l and not re.match(r'^Project Description', l, re.I):
                desc_lines.append(l)
        description = ' '.join(desc_lines).strip()
        # Strip leading colon / dash artifacts
        description = re.sub(r'^[:\-\s]+', '', description)

    # Management dept: lines between "Project Management" and "Funding Source"
    management = ''
    if i_mgmt is not None and i_fund_hdr is not None:
        mgmt_lines = []
        for l in lines[i_mgmt+1:i_fund_hdr]:
            l = l.strip()
            # Skip "Five Year" header, "Total" label, and single-char noise
            if not l or l in ('Five Year','Total') or len(l) < 3:
                continue
            mgmt_lines.append(l)
        # Management is usually 1-2 lines like "Public Works" or "Water Utility"
        management = ' '.join(mgmt_lines[:2]).strip()

    # Funding sources: rows between "Funding Source" header and "Total Funding" or "Project Cost"
    funding_rows = []
    if i_fund_hdr is not None:
        stop = i_cost_hdr if i_cost_hdr else len(lines)
        # Rows start after the header+column labels (5 labels: "Five Year Total", "FY 06-07"..."FY 10-11")
        # Look for "Total Funding" terminator inside this range
        i_total_fund = None
        for j in range(i_fund_hdr, stop):
            if re.match(r'^Total Funding', lines[j], re.I):
                i_total_fund = j; break
        # Funding data region: from after column headers up to i_total_fund
        # The exact line ordering varies — just collect money-like numbers and group them in sets of 6 (total + 5 yearly)
        region = lines[i_fund_hdr+1:(i_total_fund or stop)]
        # Identify source labels (non-numeric) and their numeric rows
        def is_hdr(l):
            ls = l.strip()
            # Match standalone column header lines, plus OCR-merged header lines
            # like "Five Year Total FY 06-07" (happens when row spacing collapses).
            if re.match(r'^(Five Year|Total|Jotal|F[Yy]\s*\d{2}-\d{2}|EY\s*\d{2}-\d{2}|Funding[\s_]?Source|Year)$', ls, re.I):
                return True
            if re.match(r'^Five\s+Year\s+Total', ls, re.I):
                return True
            return False

        def _flush(source, nums):
            if not source or len(source) < 3: return
            alpha = sum(1 for c in source if c.isalpha())
            if alpha < 3: return
            if not nums:
                return  # drop phantom rows from split/parenthetical labels
            vals = [parse_money(x) for x in nums][:6]
            while len(vals) < 6:
                vals.append(0)
            if not any(vals):
                return  # drop all-zero rows (OCR noise)
            # Reconciliation: if yearly sum diverges from stated 5-year total by
            # an order of magnitude, trust the yearly sum (OCR often drops the
            # first digit of the total). Require the yearly values to be
            # self-consistent (non-zero) before overriding.
            total = vals[0]
            yearly_sum = sum(vals[1:6])
            yearly_nonzero = sum(1 for v in vals[1:6] if v)
            data_quality = 'ok'
            if total and yearly_sum and yearly_nonzero >= 2:
                ratio = yearly_sum / total if total else float('inf')
                if ratio > 3 or ratio < 0.33:
                    data_quality = f'total_adjusted_from_{int(total)}_to_{int(yearly_sum)}'
                    total = yearly_sum
            funding_rows.append({
                'source': source,
                'five_year_total': total,
                'fy06_07': vals[1],
                'fy07_08': vals[2],
                'fy08_09': vals[3],
                'fy09_10': vals[4],
                'fy10_11': vals[5],
                'ocr_quality_note': data_quality if data_quality != 'ok' else None,
            })

        source = None
        nums_buffer = []
        for l in region:
            l = l.strip()
            if not l: continue
            if is_hdr(l): continue
            if is_numeric_line(l):
                nums_buffer.append(l)
            else:
                if len(l) < 3: continue
                alpha_ratio = sum(1 for c in l if c.isalpha()) / max(len(l),1)
                if alpha_ratio < 0.3: continue
                if source is not None:
                    if not nums_buffer:
                        # No numbers collected for the previous source — OCR
                        # probably split the source name across lines. Merge.
                        source = f'{source} {l}'
                        continue
                    _flush(source, nums_buffer)
                source = l
                nums_buffer = []
        if source is not None:
            _flush(source, nums_buffer)

    # Project costs: parse similarly
    cost_rows = []
    total_cost_row = {}
    if i_cost_hdr is not None:
        stop = i_type if i_type else len(lines)
        region = lines[i_cost_hdr+1:stop]
        label = None
        nums_buffer = []
        for l in region:
            l = l.strip()
            if not l: continue
            if re.match(r'^(Five Year|Total\s*$|Fy\s*\d{2}-\d{2}|FY\s*\d{2}-\d{2}|Project Cost)', l, re.I):
                continue
            if is_numeric_line(l):
                nums_buffer.append(l)
            else:
                if nums_buffer and label:
                    cost_rows.append({'label': label, 'vals': [parse_money(x) for x in nums_buffer[:6]]})
                label = l
                nums_buffer = []
        if nums_buffer and label:
            cost_rows.append({'label': label, 'vals': [parse_money(x) for x in nums_buffer[:6]]})
        # Identify total cost row
        for cr in cost_rows:
            if re.search(r'total\s+construction|total\s+cost', cr['label'], re.I):
                total_cost_row = cr
                break

    # Type of Project
    type_of_project = None
    if i_type is not None:
        ln = lines[i_type].strip()
        m = re.match(r'^Type of Project:?\s*(.+)', ln, re.I)
        type_of_project = m.group(1).strip() if m and m.group(1) else None
        if not type_of_project and i_type+1 < len(lines):
            type_of_project = lines[i_type+1].strip()

    # Operating budget impact
    op_budget_impact = None
    if i_impact is not None:
        ln = lines[i_impact].strip()
        m = re.match(r'^Impact on Operating Budget:?\s*(.+)', ln, re.I)
        op_budget_impact = m.group(1).strip() if m and m.group(1) else None

    # Compute 5-year total from funding sources
    five_year_total = sum((fr.get('five_year_total') or 0) for fr in funding_rows) if funding_rows else None

    return {
        'pdf_page': page_num,
        'project_name': title,
        'management_dept': management,
        'description': description,
        'type_of_project': type_of_project,
        'operating_budget_impact': op_budget_impact,
        'funding_sources': funding_rows,
        'cost_breakdown': cost_rows,
        'total_construction': total_cost_row,
        'five_year_total_funding': five_year_total,
    }


def main():
    if '--render' in sys.argv or not os.listdir(PAGE_DIR):
        render_pages()
    if '--ocr' in sys.argv or len(os.listdir(OCR_DIR)) < len(os.listdir(PAGE_DIR)):
        ocr_all()

    projects = parse_project_pages()
    print(f'\nExtracted {len(projects)} projects')

    # Active-transportation heuristic v3 — uses word boundaries to avoid
    # false positives like "trail" matching "trailers" or "bike" matching
    # unrelated mentions. Phrase keywords still use substring match.
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
    for p in projects:
        blob = ' '.join(str(p.get(k) or '') for k in ('project_name','description','type_of_project'))
        p['likely_active_transportation'] = has_at(blob)
        p['at_keywords_matched'] = at_hits(blob)

    out_path = os.path.join(HERE, 'fy0608_cip_projects.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'source': 'City of Oceanside — FY 2006-2008 Capital Improvement Program (5-year plan FY 06-07 through FY 10-11)',
            'source_pdf': 'raw_pdfs/FY0608_CIP_section.pdf',
            'extraction_method': 'EasyOCR + structured parsing of scanned PDF',
            'extracted_project_count': len(projects),
            'note': 'Scanned source — expect some OCR errors in numbers and titles. Review before publishing.',
            'projects': projects,
        }, f, indent=2, ensure_ascii=False)
    print(f'Wrote {out_path}')

    # Quick stats
    at_count = sum(1 for p in projects if p['likely_active_transportation'])
    total = sum((p.get('five_year_total_funding') or 0) for p in projects)
    at_spend = sum((p.get('five_year_total_funding') or 0) for p in projects if p['likely_active_transportation'])
    print(f'5-year planned (FY06-07..FY10-11): ${total:,.0f}')
    print(f'Active-transportation: {at_count} projects, ${at_spend:,.0f} ({at_spend/total*100 if total else 0:.1f}%)')


if __name__ == '__main__':
    main()
