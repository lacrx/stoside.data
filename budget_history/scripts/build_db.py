"""Build budget_history.sqlite from inventory.json and data_model.json."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
INV = ROOT / "inventory.json"
MODEL = ROOT / "data_model.json"
DB = ROOT / "budget_history.sqlite"

SCHEMA = """
DROP TABLE IF EXISTS documents;
CREATE TABLE documents (
    doc_id        TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    source_category TEXT NOT NULL,
    fiscal_year   TEXT,
    url           TEXT NOT NULL,
    timestamp     TEXT,
    local_path    TEXT,
    size_bytes    INTEGER,
    sha256        TEXT,
    pages         INTEGER,
    words         INTEGER
);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_fiscal_year ON documents(fiscal_year);

DROP TABLE IF EXISTS gf_line_items;
CREATE TABLE gf_line_items (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    basis         TEXT NOT NULL,
    flow          TEXT NOT NULL,
    category      TEXT NOT NULL,
    amount_usd    REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    source_doc_fy TEXT NOT NULL,
    source_page   INTEGER,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_gf_year_basis_flow ON gf_line_items(fiscal_year, basis, flow);
CREATE INDEX idx_gf_category ON gf_line_items(category);

DROP TABLE IF EXISTS fte_by_department;
CREATE TABLE fte_by_department (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    department    TEXT NOT NULL,
    fte           REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_fte_year_dept ON fte_by_department(fiscal_year, department);

DROP TABLE IF EXISTS measure_x;
CREATE TABLE measure_x (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    line_item     TEXT NOT NULL,           -- Taxes / Fund Balance Ending / etc.
    kind          TEXT NOT NULL,           -- revenue / expenditure / transfer / balance / net
    fund_type     TEXT NOT NULL,           -- Operating / Capital / Total
    amount_usd    REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_mx_year ON measure_x(fiscal_year);
CREATE INDEX idx_mx_item ON measure_x(line_item);

DROP TABLE IF EXISTS acfr_gf_balance;
CREATE TABLE acfr_gf_balance (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    line_item     TEXT NOT NULL,           -- fb_nonspendable / fb_restricted / fb_committed / fb_assigned / fb_unassigned / fb_total / total_assets / total_liabilities / gov_funds_total_fb
    amount_usd    REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_gfb_year ON acfr_gf_balance(fiscal_year);

DROP TABLE IF EXISTS acfr_net_position;
CREATE TABLE acfr_net_position (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    activity      TEXT NOT NULL,           -- Governmental / Business-Type / Total
    line_item     TEXT NOT NULL,
    amount_usd    REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_np_year ON acfr_net_position(fiscal_year);

DROP TABLE IF EXISTS quarterly_status;
CREATE TABLE quarterly_status (
    id                          INTEGER PRIMARY KEY,
    fiscal_year                 TEXT NOT NULL,
    quarter                     TEXT NOT NULL,  -- Q1 / Q2 / Q3 / Q4
    adopted_gf_revenue          REAL,
    adopted_gf_expenditure      REAL,
    adopted_all_funds_revenue   REAL,
    adopted_all_funds_expenditure REAL,
    actual_gf_revenue           REAL,
    actual_gf_expenditure       REAL,
    gf_surplus                  REAL,
    source_doc_id               TEXT NOT NULL,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_qs_year_quarter ON quarterly_status(fiscal_year, quarter);

DROP TABLE IF EXISTS cip_program;
CREATE TABLE cip_program (
    id            INTEGER PRIMARY KEY,
    fiscal_year   TEXT NOT NULL,
    program       TEXT NOT NULL,
    fund_id       TEXT,
    amount_usd    REAL NOT NULL,
    source_doc_id TEXT NOT NULL,
    source_doc_fy TEXT NOT NULL,
    source_page   INTEGER,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_cip_year ON cip_program(fiscal_year);
CREATE INDEX idx_cip_prog ON cip_program(program);

-- Strong Towns Finance Decoder: 11 input line items per ACFR year.
DROP TABLE IF EXISTS acfr_decoder_inputs;
CREATE TABLE acfr_decoder_inputs (
    id                   INTEGER PRIMARY KEY,
    fiscal_year          TEXT NOT NULL,
    cap_not_dep_gov      REAL,
    cap_not_dep_biz      REAL,
    cap_not_dep_total    REAL,
    cap_net_dep_gov      REAL,
    cap_net_dep_biz      REAL,
    cap_net_dep_total    REAL,
    gov_expenses         REAL,
    gov_charges          REAL,
    gov_op_grants        REAL,
    gov_cap_grants       REAL,
    biz_expenses         REAL,
    biz_charges          REAL,
    biz_op_grants        REAL,
    biz_cap_grants       REAL,
    interest_on_debt     REAL,
    gen_revenues_total   REAL,
    change_in_np_total   REAL,
    gross_not_dep_gov    REAL,
    gross_not_dep_biz    REAL,
    gross_being_dep_gov  REAL,
    gross_being_dep_biz  REAL,
    source_doc_id        TEXT NOT NULL,
    source_np_page       INTEGER,
    source_act_page      INTEGER,
    FOREIGN KEY(source_doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX idx_adi_year ON acfr_decoder_inputs(fiscal_year);

-- Strong Towns Finance Decoder: 7 metrics per year.
DROP TABLE IF EXISTS decoder_metrics;
CREATE TABLE decoder_metrics (
    id                                INTEGER PRIMARY KEY,
    fiscal_year                       TEXT NOT NULL,
    current_assets                    REAL,
    capital_assets                    REAL,
    total_assets                      REAL,
    deferred_outflows                 REAL,
    liabilities                       REAL,
    deferred_inflows                  REAL,
    total_liabilities                 REAL,
    total_revenues                    REAL,
    op_grants                         REAL,
    cap_grants                        REAL,
    interest_charges                  REAL,
    net_book_tca                      REAL,
    total_cost_tca                    REAL,
    metric_1_net_financial_position   REAL,
    metric_2_financial_assets_to_liab REAL,
    metric_3_total_assets_to_liab     REAL,
    metric_4_net_debt_to_revenues     REAL,
    metric_5_interest_to_revenues     REAL,
    metric_6_net_book_to_cost_tca     REAL,
    metric_7_transfers_to_revenues    REAL
);
CREATE INDEX idx_dm_year ON decoder_metrics(fiscal_year);

-- Convenience view: authoritative GF summary per year
-- Actuals taken from the most recent budget's historical column;
-- Adopted taken from that year's own adopted budget.
DROP VIEW IF EXISTS gf_authoritative;
CREATE VIEW gf_authoritative AS
SELECT
    g.fiscal_year,
    g.basis,
    g.flow,
    g.category,
    g.amount_usd,
    g.source_doc_id,
    g.source_doc_fy
FROM gf_line_items g
WHERE g.id IN (
    SELECT MIN(id) FROM gf_line_items g2
    WHERE g2.fiscal_year = g.fiscal_year
      AND g2.basis = g.basis
      AND g2.flow = g.flow
      AND g2.category = g.category
      AND g2.source_doc_fy = (
        SELECT MAX(source_doc_fy) FROM gf_line_items g3
        WHERE g3.fiscal_year = g2.fiscal_year
          AND g3.basis = g2.basis
          AND g3.flow = g2.flow
          AND g3.category = g2.category
      )
);
"""


def main():
    inv = json.loads(INV.read_text())
    model = json.loads(MODEL.read_text())

    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    for r in inv:
        conn.execute(
            """INSERT INTO documents
            (doc_id, title, doc_type, source_category, fiscal_year, url, timestamp,
             local_path, size_bytes, sha256, pages, words)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["doc_id"], r["title"], r["doc_type"], r["source_category"],
                r.get("fiscal_year"), r["url"], r.get("timestamp"),
                r.get("local_path"), r.get("size_bytes"), r.get("sha256"),
                r.get("pages"), r.get("words"),
            ),
        )

    for r in model.get("general_fund", []):
        conn.execute(
            """INSERT INTO gf_line_items
            (fiscal_year, basis, flow, category, amount_usd,
             source_doc_id, source_doc_fy, source_page)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["fiscal_year"], r["basis"], r["flow"], r["category"],
                r["amount_usd"], r["source_doc_id"], r["source_doc_fy"],
                r.get("source_page_idx"),
            ),
        )

    for r in model.get("fte_by_department", []):
        conn.execute(
            """INSERT INTO fte_by_department (fiscal_year, department, fte, source_doc_id)
            VALUES (?, ?, ?, ?)""",
            (r["fiscal_year"], r["department"], r["fte"], r["source_doc_id"]),
        )

    for r in model.get("measure_x", []):
        conn.execute(
            """INSERT INTO measure_x (fiscal_year, line_item, kind, fund_type, amount_usd, source_doc_id)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (r["fiscal_year"], r["line_item"], r["kind"], r["fund_type"],
             r["amount_usd"], r["source_doc_id"]),
        )

    for r in model.get("acfr_gf_balance", []):
        conn.execute(
            """INSERT INTO acfr_gf_balance (fiscal_year, line_item, amount_usd, source_doc_id)
            VALUES (?, ?, ?, ?)""",
            (r["fiscal_year"], r["line_item"], r["amount_usd"], r["source_doc_id"]),
        )

    for r in model.get("acfr_net_position", []):
        conn.execute(
            """INSERT INTO acfr_net_position (fiscal_year, activity, line_item, amount_usd, source_doc_id)
            VALUES (?, ?, ?, ?, ?)""",
            (r["fiscal_year"], r["activity"], r["line_item"], r["amount_usd"], r["source_doc_id"]),
        )

    for r in model.get("quarterly", []):
        conn.execute(
            """INSERT INTO quarterly_status
            (fiscal_year, quarter, adopted_gf_revenue, adopted_gf_expenditure,
             adopted_all_funds_revenue, adopted_all_funds_expenditure,
             actual_gf_revenue, actual_gf_expenditure, gf_surplus, source_doc_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["fiscal_year"], r["quarter"],
                r.get("adopted_gf_revenue"), r.get("adopted_gf_expenditure"),
                r.get("adopted_all_funds_revenue"), r.get("adopted_all_funds_expenditure"),
                r.get("actual_gf_revenue"), r.get("actual_gf_expenditure"),
                r.get("gf_surplus"), r["source_doc_id"],
            ),
        )

    for r in model.get("cip_program", []):
        conn.execute(
            """INSERT INTO cip_program (fiscal_year, program, fund_id, amount_usd,
                source_doc_id, source_doc_fy, source_page)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (r["fiscal_year"], r["program"], r.get("fund_id"), r["amount_usd"],
             r["source_doc_id"], r["source_doc_fy"], r.get("source_page_idx")),
        )

    for r in model.get("acfr_decoder_inputs", []):
        conn.execute(
            """INSERT INTO acfr_decoder_inputs
            (fiscal_year, cap_not_dep_gov, cap_not_dep_biz, cap_not_dep_total,
             cap_net_dep_gov, cap_net_dep_biz, cap_net_dep_total,
             gov_expenses, gov_charges, gov_op_grants, gov_cap_grants,
             biz_expenses, biz_charges, biz_op_grants, biz_cap_grants,
             interest_on_debt, gen_revenues_total, change_in_np_total,
             gross_not_dep_gov, gross_not_dep_biz,
             gross_being_dep_gov, gross_being_dep_biz,
             source_doc_id, source_np_page, source_act_page)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["fiscal_year"],
                r.get("cap_not_dep_gov"), r.get("cap_not_dep_biz"), r.get("cap_not_dep_total"),
                r.get("cap_net_dep_gov"), r.get("cap_net_dep_biz"), r.get("cap_net_dep_total"),
                r.get("gov_expenses"), r.get("gov_charges"),
                r.get("gov_op_grants"), r.get("gov_cap_grants"),
                r.get("biz_expenses"), r.get("biz_charges"),
                r.get("biz_op_grants"), r.get("biz_cap_grants"),
                r.get("interest_on_debt"),
                r.get("gen_revenues_total"), r.get("change_in_np_total"),
                r.get("gross_not_dep_gov"), r.get("gross_not_dep_biz"),
                r.get("gross_being_dep_gov"), r.get("gross_being_dep_biz"),
                r.get("source_doc_id", ""),
                r.get("source_np_page"), r.get("source_act_page"),
            ),
        )

    for r in model.get("decoder_metrics", []):
        conn.execute(
            """INSERT INTO decoder_metrics
            (fiscal_year, current_assets, capital_assets, total_assets,
             deferred_outflows, liabilities, deferred_inflows, total_liabilities,
             total_revenues, op_grants, cap_grants, interest_charges,
             net_book_tca, total_cost_tca,
             metric_1_net_financial_position, metric_2_financial_assets_to_liab,
             metric_3_total_assets_to_liab, metric_4_net_debt_to_revenues,
             metric_5_interest_to_revenues, metric_6_net_book_to_cost_tca,
             metric_7_transfers_to_revenues)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["fiscal_year"],
                r.get("current_assets"), r.get("capital_assets"), r.get("total_assets"),
                r.get("deferred_outflows"), r.get("liabilities"), r.get("deferred_inflows"),
                r.get("total_liabilities"), r.get("total_revenues"),
                r.get("op_grants"), r.get("cap_grants"),
                r.get("interest_charges"), r.get("net_book_tca"), r.get("total_cost_tca"),
                r.get("metric_1_net_financial_position"),
                r.get("metric_2_financial_assets_to_liab"),
                r.get("metric_3_total_assets_to_liab"),
                r.get("metric_4_net_debt_to_revenues"),
                r.get("metric_5_interest_to_revenues"),
                r.get("metric_6_net_book_to_cost_tca"),
                r.get("metric_7_transfers_to_revenues"),
            ),
        )

    conn.commit()
    stats = {}
    for t in ["documents", "gf_line_items", "fte_by_department",
              "measure_x", "acfr_gf_balance", "acfr_net_position",
              "quarterly_status", "cip_program",
              "acfr_decoder_inputs", "decoder_metrics"]:
        stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    conn.close()
    print(f"built {DB}")
    for t, c in stats.items():
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
