"""Visualizations for Oceanside CIP dataset.

Produces:
- cip_overview.png — 4-panel overview (totals, top AT projects, by category, coverage)
- cip_mode_split.png — AT vs car-oriented spending (main user-facing question)
"""
import json, os
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, 'unified_cip.json'), encoding='utf-8'))
obs = d['observations']

# Colors: AT = blue (positive), auto_capacity = dark red (widening), auto_maintenance = orange (asphalt), other = grey
COLORS = {
    'active_transport': '#1f77b4',
    'auto_capacity':    '#8b0000',
    'auto_maintenance': '#ff7f0e',
    'other_infra':      '#bdbdbd',
}
LABELS = {
    'active_transport': 'Active transportation\n(bike/ped/trail/ADA/calming)',
    'auto_capacity':    'Car capacity\n(widening, new signals)',
    'auto_maintenance': 'Car maintenance\n(overlay, slurry, seismic)',
    'other_infra':      'Other infrastructure\n(parks, buildings, drainage, bridges)',
}

def era_obs(source):
    return [o for o in obs if o['source'] == source and o.get('cip_class') == 'general']


def dollars(amount):
    return f'${amount/1e6:.1f}M' if amount >= 1e6 else f'${amount/1e3:.0f}K' if amount > 0 else '$0'


# =============================================================
#  mode_split figure — headline for the user's question
# =============================================================

fy0608 = era_obs('fy0608_book')
fy2526 = era_obs('fy2526_book')

def mode_totals(era):
    tot = defaultdict(float)
    for o in era:
        tot[o.get('mode_orientation') or 'other_infra'] += (o.get('cost_5yr_total') or 0)
    return dict(tot)

t0 = mode_totals(fy0608)
t1 = mode_totals(fy2526)
MODES_ORDER = ['active_transport', 'auto_capacity', 'auto_maintenance', 'other_infra']

fig, axes = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={'width_ratios': [1, 1.3]})

# ----- Panel A: stacked bars of 5-year plan totals by mode -----
ax = axes[0]
eras = ['FY 2006-07\n→ 2010-11', 'FY 2025-26\n→ 2029-30']
totals_by_mode = {m: [t0.get(m, 0) / 1e6, t1.get(m, 0) / 1e6] for m in MODES_ORDER}

bottom = [0.0, 0.0]
for m in MODES_ORDER:
    vals = totals_by_mode[m]
    ax.bar(eras, vals, bottom=bottom, color=COLORS[m], label=LABELS[m],
           edgecolor='black', linewidth=0.5, width=0.5)
    for i, v in enumerate(vals):
        if v > 3:  # label only the biggish segments
            pct = v / sum(m2[i] for m2 in totals_by_mode.values()) * 100
            ax.text(i, bottom[i] + v / 2, f'${v:.1f}M\n{pct:.1f}%',
                    ha='center', va='center', fontsize=9, color='white' if m != 'other_infra' else 'black',
                    fontweight='bold')
    bottom = [b + v for b, v in zip(bottom, vals)]

# Total labels
for i, b in enumerate(bottom):
    ax.text(i, b + 2, f'Total ${b:.1f}M', ha='center', fontsize=11, fontweight='bold')

ax.set_ylabel('5-year plan ($ millions)')
ax.set_title('General CIP 5-year plan by mode orientation', fontweight='bold')
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.0f}M'))
ax.set_ylim(0, max(bottom) * 1.18)
ax.grid(axis='y', alpha=0.3)
ax.legend(loc='upper left', fontsize=8, framealpha=0.95)

# ----- Panel B: AT vs car-oriented side-by-side with ratio -----
ax = axes[1]
car_t0 = t0.get('auto_capacity', 0) + t0.get('auto_maintenance', 0)
car_t1 = t1.get('auto_capacity', 0) + t1.get('auto_maintenance', 0)
at_t0 = t0.get('active_transport', 0)
at_t1 = t1.get('active_transport', 0)

x = [0, 1]
w = 0.35
car_values = [car_t0 / 1e6, car_t1 / 1e6]
at_values = [at_t0 / 1e6, at_t1 / 1e6]

bars_car = ax.bar([xi - w/2 for xi in x], car_values, width=w,
                  color='#d32f2f', edgecolor='black', linewidth=0.5,
                  label='Car-oriented\n(capacity + maintenance)')
bars_at = ax.bar([xi + w/2 for xi in x], at_values, width=w,
                 color=COLORS['active_transport'], edgecolor='black', linewidth=0.5,
                 label='Active transportation')

# Labels above bars
for i in range(2):
    ax.text(i - w/2, car_values[i] + 0.8, f'${car_values[i]:.1f}M',
            ha='center', fontsize=10, fontweight='bold')
    ax.text(i + w/2, at_values[i] + 0.8, f'${at_values[i]:.1f}M',
            ha='center', fontsize=10, fontweight='bold')
    # Ratio line
    ratio = car_values[i] / at_values[i] if at_values[i] else float('inf')
    ax.text(i, max(car_values[i], at_values[i]) + 4,
            f'Car spending = {ratio:.1f}× AT',
            ha='center', fontsize=11, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.4', fc='lemonchiffon', ec='black', lw=0.5))

ax.set_xticks(x)
ax.set_xticklabels(['FY 2006-07 → 2010-11', 'FY 2025-26 → 2029-30'])
ax.set_ylabel('5-year plan ($ millions)')
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.0f}M'))
ax.set_title('Active transportation vs car-oriented spending', fontweight='bold')
ax.legend(loc='upper left', fontsize=9)
ax.grid(axis='y', alpha=0.3)
ax.set_ylim(0, max(max(car_values), max(at_values)) * 1.35)

plt.suptitle('Oceanside General CIP — how transportation dollars split between cars and people',
             fontsize=13, fontweight='bold', y=1.00)
plt.tight_layout()
plt.savefig(os.path.join(HERE, 'cip_mode_split.png'), dpi=130, bbox_inches='tight')
plt.close()


# =============================================================
#  overview figure — 4 panels (unchanged from before but rebuilt)
# =============================================================

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Oceanside Capital Improvement Program — General CIP overview',
             fontsize=14, fontweight='bold', y=0.995)

# Panel 1: AT share comparison (kept)
ax = axes[0, 0]
totals = [sum((o.get('cost_5yr_total') or 0) for o in fy0608) / 1e6,
          sum((o.get('cost_5yr_total') or 0) for o in fy2526) / 1e6]
at_totals = [sum((o.get('cost_5yr_total') or 0) for o in fy0608 if o.get('likely_active_transportation')) / 1e6,
             sum((o.get('cost_5yr_total') or 0) for o in fy2526 if o.get('likely_active_transportation')) / 1e6]
other_totals = [t - a for t, a in zip(totals, at_totals)]
x = list(range(2))
ax.bar(x, other_totals, color='#d3d3d3', label='Non-AT', edgecolor='black', linewidth=0.5)
ax.bar(x, at_totals, bottom=other_totals, color=COLORS['active_transport'],
       label='Active transportation', edgecolor='black', linewidth=0.5)
for i, (t, a) in enumerate(zip(totals, at_totals)):
    pct = a / t * 100 if t else 0
    ax.text(i, t + 2, f'${t:.1f}M total\n{pct:.1f}% AT (${a:.1f}M)',
            ha='center', fontsize=10, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(['FY 2006-07 → 2010-11', 'FY 2025-26 → 2029-30'])
ax.set_ylabel('5-year plan ($ millions)')
ax.set_title('Active-transportation share grew ~7× between eras', fontweight='bold')
ax.legend(loc='upper left')
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.0f}M'))
ax.set_ylim(0, max(totals) * 1.25)
ax.grid(axis='y', alpha=0.3)

# Panel 2: top AT projects in FY25-30 (kept)
ax = axes[0, 1]
at_projects = [o for o in fy2526 if o.get('likely_active_transportation') and (o.get('cost_5yr_total') or 0) > 0]
at_projects.sort(key=lambda o: o.get('cost_5yr_total') or 0)
at_top = at_projects[-10:]
names = [(o['project_name'] or '')[:55] for o in at_top]
amounts = [(o.get('cost_5yr_total') or 0) / 1e6 for o in at_top]
ax.barh(range(len(names)), amounts, color=COLORS['active_transport'], edgecolor='black', linewidth=0.5)
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names, fontsize=8)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.1f}M'))
ax.set_xlabel('5-year planned spend ($ millions)')
ax.set_title('Top AT projects in FY25-30 plan', fontweight='bold')
ax.grid(axis='x', alpha=0.3)
for i, v in enumerate(amounts):
    ax.text(v + 0.03, i, f'${v:.2f}M', va='center', fontsize=7)

# Panel 3: top auto-maintenance projects in FY25-30 (new — shows what the money IS going to)
ax = axes[1, 0]
auto_m = [o for o in fy2526 if o.get('mode_orientation') == 'auto_maintenance'
          and (o.get('cost_5yr_total') or 0) > 0]
auto_m.sort(key=lambda o: o.get('cost_5yr_total') or 0)
names = [(o['project_name'] or '')[:55] for o in auto_m]
amounts = [(o.get('cost_5yr_total') or 0) / 1e6 for o in auto_m]
ax.barh(range(len(names)), amounts, color=COLORS['auto_maintenance'],
        edgecolor='black', linewidth=0.5)
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names, fontsize=8)
ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.1f}M'))
ax.set_xlabel('5-year planned spend ($ millions)')
ax.set_title(f'Car-maintenance projects in FY25-30 plan (${sum(amounts):.1f}M)', fontweight='bold')
ax.grid(axis='x', alpha=0.3)
for i, v in enumerate(amounts):
    ax.text(v + 0.08, i, f'${v:.2f}M', va='center', fontsize=7)

# Panel 4: coverage timeline
ax = axes[1, 1]
coverage = [
    ('FY 2006-07 → 2010-11', 'FY06-08 CIP Book (OCR)', 2006, 2011, '#1f77b4', 75),
    ('FY 2011-12 → 2020-21', 'no per-project cost', 2011, 2021, '#d3d3d3', 0),
    ('FY 2021-22 → 2025-26', 'GIS (schedule only)', 2021, 2026, '#2ca02c', 76),
    ('FY 2025-26 → 2029-30', 'FY25-26 CIP Book', 2025, 2030, '#ff7f0e', 196),
]
for i, (label, sub, start, end, color, n) in enumerate(coverage):
    ax.barh(i, end - start, left=start, color=color, edgecolor='black', linewidth=0.5, height=0.6)
    ax.text((start + end) / 2, i, f'{sub}  (n={n})', ha='center', va='center',
            fontsize=9, color='black' if color != '#d3d3d3' else 'dimgray')
ax.set_yticks(range(len(coverage)))
ax.set_yticklabels([c[0] for c in coverage])
ax.set_xlabel('Fiscal year')
ax.set_xlim(2005, 2031)
ax.set_title('Dataset coverage timeline', fontweight='bold')
ax.invert_yaxis()
ax.grid(axis='x', alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(HERE, 'cip_overview.png'), dpi=130, bbox_inches='tight')
plt.close()

print('wrote cip_mode_split.png and cip_overview.png')
print(f'FY06-10 General CIP: AT ${at_t0/1e6:.1f}M vs Car-oriented ${car_t0/1e6:.1f}M (ratio {car_t0/at_t0:.1f}x)')
print(f'FY25-30 General CIP: AT ${at_t1/1e6:.1f}M vs Car-oriented ${car_t1/1e6:.1f}M (ratio {car_t1/at_t1:.1f}x)')
