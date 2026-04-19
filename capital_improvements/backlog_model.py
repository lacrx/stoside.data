"""Model the accumulation of Oceanside's deferred pavement maintenance backlog.

Compares actual car-infrastructure spend (from unified_cip.json auto_maintenance
+ auto_capacity) against the estimated true annual cost of keeping the road
network in steady-state condition.

Assumptions are explicit and overridable at the top of the file. This is a
modeled estimate — annotate clearly when sharing.
"""
import json, os
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------
# Network size: computed from Oceanside's own PCI spreadsheet
# (PCI/Oceanside PCI.xlsx, Raw PCI sheet — 4,311 City-owned segments surveyed).
# Lane-miles = Σ(pavement_length × pavement_width / 12ft-per-lane) across all segments.
# NB: this reflects current pavement width, which in Oceanside is typically
# wider than truly needed on many streets. A Circulation-Element-based
# minimum-width assumption (coming in a sibling General Plan folder) will
# let us refine this as "maintenance burden if lanes were at policy minimum."
CENTERLINE_MILES = 407          # actual, from PCI workbook
LANE_MILES = 1404               # actual, assuming 12 ft per lane
LANE_FACTOR = LANE_MILES / CENTERLINE_MILES   # ~3.45, higher than typical because arterials are 4-6 lanes wide

# Life-cycle cost benchmarks ($/lane-mile, from Oceanside's own Measure X page +
# industry rules of thumb). Annualized by dividing by typical cycle years.
LIFECYCLE = {
    'slurry_seal':     {'unit_cost': 25_000,    'cycle_years': 6},   # $20-30K, every 5-7 yrs
    'overlay':         {'unit_cost': 350_000,   'cycle_years': 18},  # $250-400K, every 15-20 yrs. Oside actual: $383K
    'reconstruction':  {'unit_cost': 1_500_000, 'cycle_years': 50},  # $1-2M, every 40-60 yrs
}

# City-own methodology (from the FY20-21 Breakdown sheet of the PCI workbook):
# 46.67 centerline miles of overlay needed/year at $383K/mi = $17.89M
# 100 centerline miles of slurry needed/year at $21.57K/mi = $2.16M
# Total: $20.05M/year need (overlay + slurry only, no reconstruction)
# Actual FY20-21 spend: $5.59M → $14.45M shortfall (72% underfunded).
CITY_OVERLAY_NEED_PER_YEAR = 17_888_889
CITY_SLURRY_NEED_PER_YEAR = 2_156_522
CITY_METHODOLOGY_ANNUAL_NEED = CITY_OVERLAY_NEED_PER_YEAR + CITY_SLURRY_NEED_PER_YEAR  # $20.05M

# ---------------------------------------------------------------
# SCS (Save California Streets) state-lens calibration
# ---------------------------------------------------------------
# 2022 Statewide Local Streets and Roads Needs Assessment (NCE/RCTF/RTPA,
# April 2023). This is the state-mandated biennial report that cities submit
# to in exchange for SB1 funding — the authoritative statewide benchmark.
#
# Three separate per-lane-mile/year figures are derived below from the SCS
# 10-year needs totals (constant 2022 $), then applied to Oceanside's
# 1,404-lane-mile network to get a complementary "state-lens" annual need.
#
# Pavement needs (to reach BMP — PCI in 80s, zero backlog — over 10 years):
#   Statewide: $81.0B / 10yr / 321,170 lane-mi = $25,220/lane-mi/yr
#   San Diego County (weighted by pavement area, includes all 18 SD cities):
#     $4,569M / 10yr / 18,852 lane-mi = $24,235/lane-mi/yr
# Essential components (storm drains, curb/gutter, sidewalks, curb ramps,
#   traffic signals, streetlights, traffic signs, sound walls, ADA, NPDES,
#   other physical assets):
#   Statewide: $39.0B / 10yr / 321,170 = $12,142/lane-mi/yr
#   San Diego County: $2,676M / 10yr / 18,852 = $14,196/lane-mi/yr
# Active transportation (bike facilities + pedestrian facilities excluding
#   sidewalks, which are counted in essential components):
#   Statewide: $11.2B / 10yr / 321,170 = $3,488/lane-mi/yr
#
# SCS unit costs (2022 $/sq-yd, Table 2.2, averaged over 148 agencies):
#   Preventive maintenance (seals):  $6.86 major / $6.41 local
#   Thin HMA overlay:                $26.86 major / $26.02 local
#   Thick HMA overlay:               $43.61 major / $41.66 local
#   Reconstruction:                  $99.04 major / $84.39 local
# Converting to $/lane-mile (7,040 sq-yd per 12-ft-wide lane-mile):
#   Preventive maintenance ≈ $48K/lane-mi  (vs our $25K assumption)
#   Thick overlay        ≈ $307K/lane-mi  (vs our $350K and Oceanside's $383K)
#   Reconstruction       ≈ $697K/lane-mi  (vs our $1.5M — but SCS pavement cost
#                                           excludes curb/drainage/ADA, which
#                                           are tracked in essential components)
# 14× cost-escalation rule: reconstruction at PCI<25 costs 14× more than
#   preservation at PCI≥70. Oceanside's mean PCI of 60 is *below* the
#   preservation threshold, so every year of delay moves pavement area into
#   the steep part of the cost curve.
SCS_PAVEMENT_PER_LANEMI_STATEWIDE = 25_220
SCS_PAVEMENT_PER_LANEMI_SD_COUNTY = 24_235
SCS_ESSENTIAL_PER_LANEMI_STATEWIDE = 12_142
SCS_ESSENTIAL_PER_LANEMI_SD_COUNTY = 14_196
SCS_ACTIVE_TRANSPORT_PER_LANEMI = 3_488

# Oceanside's mean PCI of 60 is meaningfully below SCS's statewide weighted
# average (65 — "at risk, positioned for rapid decline") and far below San
# Diego County's weighted average (71 — "good"; SD is one of only 4 CA
# counties in good condition, thanks to large well-maintained cities that
# outweigh Oceanside's 407 centerline miles in the area-weighted average).
SCS_PAVEMENT_ANNUAL_NEED = SCS_PAVEMENT_PER_LANEMI_SD_COUNTY * LANE_MILES
SCS_ESSENTIAL_ANNUAL_NEED = SCS_ESSENTIAL_PER_LANEMI_SD_COUNTY * LANE_MILES
SCS_ACTIVE_TRANSPORT_ANNUAL_NEED = SCS_ACTIVE_TRANSPORT_PER_LANEMI * LANE_MILES
SCS_PAVEMENT_PLUS_ESSENTIAL_ANNUAL_NEED = SCS_PAVEMENT_ANNUAL_NEED + SCS_ESSENTIAL_ANNUAL_NEED
SCS_FULL_TRANSPORTATION_ANNUAL_NEED = (
    SCS_PAVEMENT_ANNUAL_NEED + SCS_ESSENTIAL_ANNUAL_NEED + SCS_ACTIVE_TRANSPORT_ANNUAL_NEED
)

def annual_cost_per_lane_mile(scenario='mid'):
    """Returns $/lane-mile/year steady-state maintenance need."""
    # Scenario adjustments: low = best-case no reconstruction, high = full cycle with reconstruction
    mult = {'low': 0.7, 'mid': 1.0, 'high': 1.3}[scenario]
    total = 0
    for phase in LIFECYCLE.values():
        total += phase['unit_cost'] / phase['cycle_years']
    return total * mult

# Actual spend timeline. Per fiscal year (FY as end-year, e.g., 2010 = FY2009-10).
# Pre-2021 numbers are modeled from the FY06-08 CIP Book (actual) plus the City's
# own statement that "approximately $7M annually" goes to pavement management.
# FY25-30 numbers are from the FY25-26 CIP Book.
#
# FY06-08 book reports $24.4M over 5 years for auto_maintenance → $4.88M/yr avg.
# We extend that baseline plus a Measure X boost starting FY2019-20 when the tax began.
ACTUAL_SPEND = {
    # fiscal_year_end: dollars_spent_on_pavement_maintenance
    2007: 4_880_000,  2008: 4_880_000, 2009: 4_880_000, 2010: 4_880_000, 2011: 4_880_000,
    # FY11-20 not in dataset; baseline ~$5-7M/yr (city self-report)
    2012: 5_000_000, 2013: 5_000_000, 2014: 5_500_000, 2015: 6_000_000, 2016: 6_000_000,
    2017: 6_500_000, 2018: 6_500_000, 2019: 7_000_000,
    # Measure X revenue begins FY2019-20
    2020: 10_000_000,  # $7M baseline + ~$3M Measure X (Year 1)
    2021: 12_000_000,  # Year 2: overlay $4.6M + slurry $1M + baseline
    2022: 11_000_000,  # Year 3-4 mix
    2023: 12_000_000,
    2024: 12_000_000,
    2025: 12_000_000,
    # FY25-30 from the CIP book auto_maintenance totals (includes Measure X & SB1 & TransNet)
    2026: 7_400_000,
    2027: 7_400_000,
    2028: 7_400_000,
    2029: 7_400_000,
    2030: 7_400_000,
}

# ---------------------------------------------------------------
# Model
# ---------------------------------------------------------------

def run_model():
    results = {}
    years = sorted(ACTUAL_SPEND.keys())
    scenarios = {
        'city_overlay_slurry': CITY_METHODOLOGY_ANNUAL_NEED,  # city's own methodology
        'scs_pavement_only':   SCS_PAVEMENT_ANNUAL_NEED,               # SCS pavement only
        'scs_pavement_plus_essential': SCS_PAVEMENT_PLUS_ESSENTIAL_ANNUAL_NEED,
        'scs_full_transport':  SCS_FULL_TRANSPORTATION_ANNUAL_NEED,    # pavement+EC+AT
        'low':  annual_cost_per_lane_mile('low') * LANE_MILES,
        'mid':  annual_cost_per_lane_mile('mid') * LANE_MILES,
        'high': annual_cost_per_lane_mile('high') * LANE_MILES,
    }
    for scenario, annual_need in scenarios.items():
        cumulative = 0
        rows = []
        for y in years:
            spend = ACTUAL_SPEND[y]
            gap = max(0, annual_need - spend)
            cumulative += gap
            rows.append({
                'fiscal_year_end': y,
                'actual_spend': spend,
                'true_annual_need': annual_need,
                'annual_gap': gap,
                'cumulative_backlog': cumulative,
            })
        results[scenario] = {
            'annual_need': annual_need,
            'final_backlog': cumulative,
            'years': rows,
        }
    return results, years

def main():
    results, years = run_model()
    out = {
        'methodology': (
            'Backlog accumulation = annual (true cost − actual spend), summed since FY2006-07. '
            'Lane-miles computed directly from Oceanside PCI workbook (Raw PCI sheet). '
            'Four scenarios: (city_overlay_slurry) uses the City\'s own FY20-21 '
            'methodology of overlay+slurry only; (low/mid/high) add reconstruction '
            'life-cycle costs with increasing aggressiveness.'
        ),
        'assumptions': {
            'centerline_miles': CENTERLINE_MILES,
            'lane_factor': LANE_FACTOR,
            'lane_miles': LANE_MILES,
            'source': 'PCI/Oceanside PCI.xlsx — Raw PCI sheet (4311 segments)',
            'current_network_avg_pci': 60,
            'current_pci_distribution': {
                'poor_failing': '30.2%',
                'at_risk': '21.6%',
                'good_fair': '33.6%',
                'excellent_very_good': '14.6%',
            },
            'lifecycle': LIFECYCLE,
            'scenarios': {
                'city_overlay_slurry': 'City-own methodology from FY20-21 Breakdown sheet: overlay+slurry at measured rates, no reconstruction',
                'scs_pavement_only': 'Save California Streets 2022: San Diego County pavement $/lane-mile × Oceanside lane-miles. BMP-in-10-years funding rate.',
                'scs_pavement_plus_essential': 'SCS pavement + essential components (storm drains, curb/gutter, sidewalks, curb ramps, signals, streetlights, signs, ADA, NPDES).',
                'scs_full_transport': 'SCS full transportation: pavement + essential components + active transportation (bike + ped facilities excluding sidewalks).',
                'low':  'industry lifecycle, best-case — lower unit costs, longer cycles',
                'mid':  'standard industry life-cycle mix (headline prior to SCS integration)',
                'high': 'full reconstruction rotation + inflation headroom',
            },
            'scs_source': {
                'report': 'California Statewide Local Streets and Roads Needs Assessment (April 2023)',
                'url': 'https://savecaliforniastreets.org/wp-content/uploads/2023/05/Statewide-Needs-2022-FINAL.pdf',
                'per_lane_mile_year_2022_dollars': {
                    'pavement_statewide':        SCS_PAVEMENT_PER_LANEMI_STATEWIDE,
                    'pavement_sd_county':        SCS_PAVEMENT_PER_LANEMI_SD_COUNTY,
                    'essential_statewide':       SCS_ESSENTIAL_PER_LANEMI_STATEWIDE,
                    'essential_sd_county':       SCS_ESSENTIAL_PER_LANEMI_SD_COUNTY,
                    'active_transport_statewide': SCS_ACTIVE_TRANSPORT_PER_LANEMI,
                },
                'statewide_benchmarks': {
                    'mean_pci_2022': 65,
                    'sd_county_pci_2022': 71,
                    'oceanside_pci_2022': 60,
                    'reconstruction_vs_preservation_cost_ratio': 14,
                },
            },
        },
        'calibration': {
            'city_fy2021_stated_shortfall': 14_453_411,
            'city_fy2021_actual_spend': 5_592_000,
            'city_fy2021_investment_needed': 20_045_411,
            'note': 'PCI workbook Breakdown sheet records these values for FY20-21 — use as the strongest anchor point for the analysis.',
        },
        'results': {k: {
            'annual_need': v['annual_need'],
            'final_backlog_fy2030': v['final_backlog'],
            'years': v['years'],
        } for k, v in results.items()},
    }
    with open(os.path.join(HERE, 'pavement_backlog_model.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)

    # --- Plot ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 11), gridspec_kw={'height_ratios': [1, 1]})

    # Panel 1: annual spend vs need (headline = SCS pavement + essential components)
    headline = results['scs_pavement_plus_essential']
    x = [r['fiscal_year_end'] for r in headline['years']]
    spend = [r['actual_spend'] / 1e6 for r in headline['years']]
    need = headline['annual_need'] / 1e6
    need_low = results['low']['annual_need'] / 1e6
    need_high = results['high']['annual_need'] / 1e6
    need_city = results['city_overlay_slurry']['annual_need'] / 1e6
    need_scs_pave = results['scs_pavement_only']['annual_need'] / 1e6
    need_scs_full = results['scs_full_transport']['annual_need'] / 1e6

    ax1.bar(x, spend, color='#ff7f0e', edgecolor='black', linewidth=0.4,
            label='Actual spend on car infrastructure', width=0.7)
    ax1.axhspan(need_low, need_high, color='#8b0000', alpha=0.12,
                label=f'Industry scenario range (${need_low:.0f}M–${need_high:.0f}M/yr)')
    ax1.axhline(need_city, color='#1f77b4', lw=2, linestyle=':',
                label=f'City methodology — overlay+slurry only (~${need_city:.0f}M/yr)')
    ax1.axhline(need_scs_pave, color='#2ca02c', lw=2, linestyle='-.',
                label=f'SCS pavement only (SD County rate, ~${need_scs_pave:.0f}M/yr)')
    ax1.axhline(need, color='#8b0000', lw=2.5, linestyle='--',
                label=f'SCS pavement + essential components — HEADLINE (~${need:.0f}M/yr)')
    ax1.axhline(need_scs_full, color='#4b0082', lw=2, linestyle='--',
                label=f'SCS full transportation (+ active transport, ~${need_scs_full:.0f}M/yr)')
    ax1.set_ylim(0, max(need_high, need_scs_full) * 1.30)
    ax1.set_ylabel('$ millions / year')
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.0f}M'))
    ax1.set_title('Annual car-maintenance spend vs true cost', fontweight='bold')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_xticks(x[::2])
    ax1.set_xticklabels([f'FY{y-1:02d}-{y%100:02d}' for y in x[::2]], rotation=35, ha='right', fontsize=8)

    # Annotate modeled vs actual regions
    ax1.axvspan(2011.5, 2019.5, color='gray', alpha=0.10, zorder=0)
    ax1.text(2015.5, need * 1.08, 'modeled from city-stated\n"~$7M/yr" baseline',
             ha='center', fontsize=9, color='dimgray', style='italic')
    ax1.axvspan(2006.5, 2011.5, color='#1f77b4', alpha=0.08, zorder=0)
    ax1.text(2009, need * 1.08, 'FY06-08 CIP Book\n(actual)', ha='center', fontsize=9, color='#1f77b4', style='italic')
    ax1.axvspan(2019.5, 2025.5, color='#2ca02c', alpha=0.08, zorder=0)
    ax1.text(2022.5, need * 1.08, 'Measure X era\n(partial)', ha='center', fontsize=9, color='#2ca02c', style='italic')
    ax1.axvspan(2025.5, 2030.5, color='#ff7f0e', alpha=0.08, zorder=0)
    ax1.text(2028, need * 1.08, 'FY25-26 CIP Book\n(adopted)', ha='center', fontsize=9, color='#8b5a00', style='italic')

    # Panel 2: cumulative backlog (scenarios)
    for scn, color, label in [
        ('city_overlay_slurry',        '#1f77b4', 'City methodology (overlay+slurry only)'),
        ('scs_pavement_only',          '#2ca02c', 'SCS pavement only (SD County rate)'),
        ('scs_pavement_plus_essential','#8b0000', 'SCS pavement + essential components — HEADLINE'),
        ('scs_full_transport',         '#4b0082', 'SCS full transport (+ active transport)'),
        ('mid',                        '#e55b00', 'Industry mid (prior headline)'),
    ]:
        y = [r['cumulative_backlog'] / 1e6 for r in results[scn]['years']]
        ax2.plot(x, y, lw=2.5, marker='o', color=color, label=f'{label}  → ${y[-1]:.0f}M by FY30')
        ax2.fill_between(x, 0, y, color=color, alpha=0.10)

    ax2.set_ylabel('Cumulative backlog ($ millions)')
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f'${v:.0f}M'))
    ax2.set_title('Cumulative deferred-maintenance backlog since FY 2006-07', fontweight='bold')
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(axis='y', alpha=0.3)
    ax2.set_xticks(x[::2])
    ax2.set_xticklabels([f'FY{y-1:02d}-{y%100:02d}' for y in x[::2]], rotation=35, ha='right', fontsize=8)

    # Add footer with assumption call-out
    fig.text(0.5, 0.01,
             f'Network: {LANE_MILES:,} lane-miles ({CENTERLINE_MILES} centerline × {LANE_FACTOR:.2f} avg lanes), computed from Oceanside PCI workbook (4,311 segments, Mean PCI = 60). '
             f'Headline calibrated to Save California Streets 2022 (SB1-mandated biennial needs assessment): '
             f'${SCS_PAVEMENT_PER_LANEMI_SD_COUNTY:,}/lane-mi pavement + ${SCS_ESSENTIAL_PER_LANEMI_SD_COUNTY:,}/lane-mi essential components (SD County 10-yr rates, 2022 $).',
             ha='center', fontsize=8, style='italic', color='dimgray')

    plt.suptitle('Oceanside — true cost of car infrastructure vs actual spend',
                 fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout(rect=[0, 0.03, 1, 0.99])
    plt.savefig(os.path.join(HERE, 'pavement_backlog.png'), dpi=130, bbox_inches='tight')

    # Print summary
    print(f'Network: {LANE_MILES:.0f} lane-miles ({CENTERLINE_MILES} centerline × {LANE_FACTOR:.2f})')
    for scn in ['city_overlay_slurry','scs_pavement_only','scs_pavement_plus_essential','scs_full_transport','low','mid','high']:
        v = results[scn]
        print(f'  [{scn:28s}]  true annual need = ${v["annual_need"]/1e6:5.1f}M   '
              f'cumulative backlog by FY2030 = ${v["final_backlog"]/1e6:,.0f}M')
    print('wrote pavement_backlog.png + pavement_backlog_model.json')


if __name__ == '__main__':
    main()
