"""Compute the 7 Strong Towns Decoder metrics from acfr_decoder_inputs + the
existing acfr_net_position table. Writes output:

  1. decoder_metrics table in data_model.json
  2. output.xlsx that mirrors the decoder worksheet's Input sheet layout

The 11 Decoder inputs per year:
   current_assets, capital_assets, total_assets (derived),
   deferred_outflows, liabilities, deferred_inflows, total_liabilities (derived),
   total_revenues, op_grants, cap_grants, interest_charges,
   net_book_tca, total_cost_tca

The 7 metrics:
   net_financial_position        = current_assets - total_liabilities
   financial_assets_to_liab      = current_assets / total_liabilities
   total_assets_to_liab          = (total_assets + def_outflows) / total_liabilities
   net_debt_to_revenues          = max(0, -net_fin_pos) / total_revenues
   interest_to_revenues          = interest_charges / total_revenues
   net_book_to_cost_tca          = net_book_tca / total_cost_tca
   govt_transfers_to_revenues    = (op_grants + cap_grants) / total_revenues

For Total Revenues we derive from Change in Net Position + Total Expenses
(since the Statement of Activities "Total general revenues" value couldn't
be reliably extracted from every year's pymupdf output).
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MODEL = ROOT / "data_model.json"
DB = ROOT / "budget_history.sqlite"


def main():
    model = json.loads(MODEL.read_text())
    # Deduplicate inputs by fiscal_year. Pre-FY 2010 AFRs are split into 3
    # doc_ids per year (Introductory / Financial / Statistical sections) and
    # only the Financial Section yields extracted values — keep the row with
    # the most non-null fields.
    inputs_by_fy: dict[str, dict] = {}
    for r in model.get("acfr_decoder_inputs", []):
        fy = r.get("fiscal_year")
        if fy is None:
            continue
        n_filled = sum(1 for v in r.values() if v is not None)
        existing = inputs_by_fy.get(fy)
        if existing is None or n_filled > sum(1 for v in existing.values() if v is not None):
            inputs_by_fy[fy] = r
    conn = sqlite3.connect(DB)

    # Pull NP totals for all years from sqlite
    np = {}
    for r in conn.execute(
        "SELECT fiscal_year, line_item, amount_usd FROM acfr_net_position "
        "WHERE activity='Total'"
    ):
        np.setdefault(r[0], {})[r[1]] = r[2]

    all_years = sorted(set(list(inputs_by_fy.keys()) + list(np.keys())))
    # Keep single-year labels FY2002..FY2025 (budget labels like FY2019-2020 excluded).
    # Pre-2019 years were added 2026-04-18 when the corpus expanded back to
    # FY 2001. Decoder inputs will be incomplete for many of those years (see
    # HISTORY.md section on data-quality notes) but include them — the merge
    # logic yields whatever was extractable.
    years = []
    for y in all_years:
        if len(y) == 6 and y.startswith("FY"):
            try:
                yr = int(y[2:])
                if 2002 <= yr <= 2025:
                    years.append(y)
            except ValueError:
                pass

    rows = []
    for i, fy in enumerate(years):
        inp = inputs_by_fy.get(fy, {})
        npy = np.get(fy, {})

        # Raw inputs — treat 0 (and absurdly small values < $1M) as missing.
        # A real city with 400+ employees and billions in infrastructure
        # never has $18 total assets; seeing it means the parser picked up
        # a page number or similar noise. This guard prevents nonsense
        # derived values like current_assets = -capital_assets.
        def _nz(v):
            if v is None or v == 0:
                return None
            if abs(v) < 1_000_000:  # below $1M is extraction noise
                return None
            return v

        total_assets = _nz(npy.get("total_assets"))
        def_outflows = _nz(npy.get("total_deferred_outflows"))
        liabilities = _nz(npy.get("total_liabilities"))
        def_inflows = _nz(npy.get("total_deferred_inflows"))
        cap_not_dep = inp.get("cap_not_dep_total")
        cap_net_dep = inp.get("cap_net_dep_total")
        capital_assets = None
        if cap_not_dep is not None and cap_net_dep is not None:
            capital_assets = cap_not_dep + cap_net_dep

        # Current Assets = Total Assets - Capital Assets. Require the result
        # to be positive; a negative figure means total_assets was likely
        # under-extracted, so flag as missing rather than propagate garbage.
        current_assets = None
        if total_assets is not None and capital_assets is not None:
            ca = total_assets - capital_assets
            if ca > 0:
                current_assets = ca

        # Total Liabilities = Liabilities + Deferred Inflows. GASB 65 introduced
        # Deferred Inflows of Resources in FY 2014; pre-FY 2014 reports lack
        # that line entirely, so missing = $0 (not "value unknown"). If
        # liabilities is present we can compute total_liab without def_inflows.
        total_liab = None
        if liabilities is not None:
            total_liab = liabilities + (def_inflows or 0)

        # Total Expenses (from our parser) = gov_expenses + biz_expenses
        total_expenses = None
        ge = inp.get("gov_expenses")
        be = inp.get("biz_expenses")
        if ge is not None:
            total_expenses = ge + (be or 0)

        # Change in Net Position via np totals (needs previous year)
        change_in_np = None
        np_total_this = npy.get("np_total")
        prev_fy = f"FY{int(fy[2:]) - 1}"
        prev_np = np.get(prev_fy, {}).get("np_total")
        if np_total_this is not None and prev_np is not None:
            change_in_np = np_total_this - prev_np

        # Total Revenues = Change in NP + Total Expenses
        total_revenues = None
        if change_in_np is not None and total_expenses is not None:
            total_revenues = change_in_np + total_expenses

        # Alternate: if we have gen_revenues_total, use it directly:
        # TR = program_revenues + gen_revenues
        if "gen_revenues_total" in inp:
            pr = (inp.get("gov_charges") or 0) + (inp.get("biz_charges") or 0) \
               + (inp.get("gov_op_grants") or 0) + (inp.get("biz_op_grants") or 0) \
               + (inp.get("gov_cap_grants") or 0) + (inp.get("biz_cap_grants") or 0)
            total_revenues = pr + inp["gen_revenues_total"]

        # Operating + Capital Grants (governmental side only — Decoder convention)
        op_grants = inp.get("gov_op_grants")
        cap_grants = inp.get("gov_cap_grants")

        interest = inp.get("interest_on_debt")

        net_book_tca = cap_net_dep  # Decoder row 19 = Capital assets, net of depreciation TOTAL

        # Total Cost of TCA = gross not-dep + gross being-dep (gov + biz each)
        # If we don't have gross being-dep, approximate via net + accumulated depreciation
        # (not available). Fall back to net_book_tca + cap_not_dep as a lower bound, but
        # that's the NET BOOK value, not gross. For now, flag missing.
        total_cost_tca = None
        if all(k in inp and inp[k] not in (None, 0) for k in
               ("gross_not_dep_gov", "gross_not_dep_biz",
                "gross_being_dep_gov", "gross_being_dep_biz")):
            total_cost_tca = (inp["gross_not_dep_gov"] + inp["gross_not_dep_biz"]
                              + inp["gross_being_dep_gov"] + inp["gross_being_dep_biz"])
            # Sanity check: total cost should be ≥ net book value (depreciation
            # never makes cost smaller than net). If not, extraction is wrong.
            if cap_net_dep is not None and total_cost_tca < cap_net_dep:
                total_cost_tca = None

        # Total Revenues must be positive for percentage metrics to make sense.
        if total_revenues is not None and total_revenues <= 0:
            total_revenues = None

        # Compute the 7 metrics
        metrics = {
            "fiscal_year": fy,
            "current_assets": current_assets,
            "capital_assets": capital_assets,
            "total_assets": total_assets,
            "deferred_outflows": def_outflows,
            "liabilities": liabilities,
            "deferred_inflows": def_inflows,
            "total_liabilities": total_liab,
            "total_revenues": total_revenues,
            "op_grants": op_grants,
            "cap_grants": cap_grants,
            "interest_charges": interest,
            "net_book_tca": net_book_tca,
            "total_cost_tca": total_cost_tca,
        }

        def safe_div(a, b):
            if a is None or b is None or b == 0:
                return None
            return a / b

        net_fin_pos = None
        if current_assets is not None and total_liab is not None:
            net_fin_pos = current_assets - total_liab

        metrics["metric_1_net_financial_position"] = net_fin_pos
        metrics["metric_2_financial_assets_to_liab"] = safe_div(current_assets, total_liab)
        if total_assets is not None and def_outflows is not None and total_liab is not None:
            metrics["metric_3_total_assets_to_liab"] = (total_assets + def_outflows) / total_liab
        else:
            metrics["metric_3_total_assets_to_liab"] = None
        if net_fin_pos is not None and total_revenues is not None:
            metrics["metric_4_net_debt_to_revenues"] = max(0, -net_fin_pos) / total_revenues
        else:
            metrics["metric_4_net_debt_to_revenues"] = None
        metrics["metric_5_interest_to_revenues"] = safe_div(interest, total_revenues)
        metrics["metric_6_net_book_to_cost_tca"] = safe_div(net_book_tca, total_cost_tca)
        trans = None
        if op_grants is not None and cap_grants is not None:
            trans = op_grants + cap_grants
        metrics["metric_7_transfers_to_revenues"] = safe_div(trans, total_revenues)

        rows.append(metrics)

    model["decoder_metrics"] = rows
    MODEL.write_text(json.dumps(model, indent=2))

    # Pretty-print a summary
    def fmt_m(v): return f"${v/1e6:>7.1f}M" if v is not None else "      -"
    def fmt_r(v): return f"{v:>7.2%}" if v is not None else "      -"
    def fmt_x(v): return f"{v:>7.2f}x" if v is not None else "      -"
    print(f"\n{'FY':6}  {'CurAss':>9} {'CapAss':>9} {'TotAss':>9} {'TotLiab':>9} {'TotRev':>9} {'NetBk':>9} {'GrossTCA':>10}")
    for r in rows:
        print(f"{r['fiscal_year']:6}  {fmt_m(r['current_assets'])} {fmt_m(r['capital_assets'])} "
              f"{fmt_m(r['total_assets'])} {fmt_m(r['total_liabilities'])} "
              f"{fmt_m(r['total_revenues'])} {fmt_m(r['net_book_tca'])} {fmt_m(r['total_cost_tca'])}")
    print(f"\n{'FY':6}  {'NetFP':>10} {'FA/L':>8} {'TA/L':>8} {'ND/R':>8} {'Int/R':>8} {'NB/TCA':>8} {'Tr/R':>8}")
    for r in rows:
        print(f"{r['fiscal_year']:6}  {fmt_m(r['metric_1_net_financial_position']):>10} "
              f"{fmt_x(r['metric_2_financial_assets_to_liab']):>8} "
              f"{fmt_x(r['metric_3_total_assets_to_liab']):>8} "
              f"{fmt_r(r['metric_4_net_debt_to_revenues']):>8} "
              f"{fmt_r(r['metric_5_interest_to_revenues']):>8} "
              f"{fmt_r(r['metric_6_net_book_to_cost_tca']):>8} "
              f"{fmt_r(r['metric_7_transfers_to_revenues']):>8}")


if __name__ == "__main__":
    main()
