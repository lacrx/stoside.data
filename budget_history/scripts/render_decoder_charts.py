"""Render the 7 Strong Towns Finance Decoder shareable charts for Oceanside
using the Canva PNG templates as backgrounds.

For each metric:
  1. Generate a matplotlib chart (dark theme matching the template style)
     with Oceanside's time series values.
  2. Composite the chart over the template's "Drag graph here" drop zone.
  3. Replace "City Name, State/Province" with "Oceanside, California".
  4. Write to decoder/populated/<metric>.png.

Data source: decoder_metrics table in budget_history.sqlite.
"""
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
DB = ROOT / "budget_history.sqlite"
TEMPLATE_DIR = ROOT / "decoder" / "Finance Decoder Shareable Template"
OUT_DIR = ROOT / "decoder" / "populated"

# Drop zone on the 1080x1080 templates — measured visually.
# Covers the example-graph mockup + the "Drag graph from Uploads and drop here"
# instruction text that sits below/beside it.
DROP_X = 40
DROP_Y = 115
DROP_W = 820
DROP_H = 500

# "City Name, State/Province" header location (dark teal bar at top)
HEADER_BOX = (30, 20, 1050, 95)

# Template-style dark teal colors
BG_COLOR = "#142D3E"      # dark teal background
PLOT_BG = "#1D3B4F"       # slightly lighter panel
LINE_COLOR = "#F5F5F0"    # off-white line
ACCENT = "#F28A4C"        # orange accent (matches Strong Towns brand)
GRID_COLOR = "#2F5268"
TEXT_COLOR = "#F5F5F0"


# Map each template file to (metric column, chart title, y-axis format, higher-is-better)
METRICS = {
    "Net Financial Position.png": {
        "col": "metric_1_net_financial_position",
        "title": "Net Financial Position ($M)",
        "yfmt": "money_millions",
        "higher_is_better": True,
    },
    "Financial Assets-to-Total Liabilities.png": {
        "col": "metric_2_financial_assets_to_liab",
        "title": "Financial Assets-to-Total Liabilities",
        "yfmt": "ratio",
        "higher_is_better": True,
    },
    "Total Assets-to-Total Liabilities.png": {
        "col": "metric_3_total_assets_to_liab",
        "title": "Total Assets-to-Total Liabilities",
        "yfmt": "ratio",
        "higher_is_better": True,
    },
    "Net Debt-to-Total Revenues.png": {
        "col": "metric_4_net_debt_to_revenues",
        "title": "Net Debt-to-Total Revenues",
        "yfmt": "percent",
        "higher_is_better": False,
    },
    "Interest-to-Total Revenues.png": {
        "col": "metric_5_interest_to_revenues",
        "title": "Interest-to-Total Revenues",
        "yfmt": "percent",
        "higher_is_better": False,
    },
    "Net Book Value-To-Cost of Tangible Capital Assets.png": {
        "col": "metric_6_net_book_to_cost_tca",
        "title": "Net Book Value-to-Cost of TCA",
        "yfmt": "percent",
        "higher_is_better": True,  # Higher = less depreciated = newer infrastructure
    },
    "Government Transfers-To-Total Revenue.png": {
        "col": "metric_7_transfers_to_revenues",
        "title": "Govt Transfers-to-Total Revenues",
        "yfmt": "percent",
        "higher_is_better": False,
    },
}


def fetch_series(col: str) -> tuple[list[str], list[float]]:
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        f"SELECT fiscal_year, {col} FROM decoder_metrics "
        f"WHERE {col} IS NOT NULL ORDER BY fiscal_year"
    ).fetchall()
    conn.close()
    years = [r[0].replace("FY", "") for r in rows]
    vals = [r[1] for r in rows]
    return years, vals


def render_chart(meta: dict, out_path: Path, width_px: int = DROP_W, height_px: int = DROP_H):
    """Generate a matplotlib chart styled to match the template."""
    years, vals = fetch_series(meta["col"])

    fig = plt.figure(figsize=(width_px / 100, height_px / 100), dpi=100)
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_subplot(111)
    ax.set_facecolor(PLOT_BG)

    if vals:
        # Convert money to millions for display
        if meta["yfmt"] == "money_millions":
            display_vals = [v / 1e6 for v in vals]
        else:
            display_vals = list(vals)

        # Plot line with markers
        ax.plot(years, display_vals, color=ACCENT, linewidth=3, marker="o",
                markersize=10, markerfacecolor=ACCENT, markeredgecolor=LINE_COLOR,
                markeredgewidth=2, zorder=3)

        # Annotate each point
        for x, y, raw in zip(years, display_vals, vals):
            if meta["yfmt"] == "percent":
                label = f"{raw*100:.1f}%"
            elif meta["yfmt"] == "ratio":
                label = f"{raw:.2f}x"
            elif meta["yfmt"] == "money_millions":
                label = f"${y:.0f}M"
            else:
                label = str(raw)
            ax.annotate(label, (x, y), textcoords="offset points", xytext=(0, 12),
                        ha="center", color=TEXT_COLOR, fontsize=11, fontweight="bold")

    # Styling
    ax.set_title(meta["title"], color=TEXT_COLOR, fontsize=14, pad=12, fontweight="bold")
    ax.tick_params(axis="both", colors=TEXT_COLOR, labelsize=11)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(True, color=GRID_COLOR, linestyle="-", linewidth=0.5, alpha=0.5, zorder=1)
    ax.set_axisbelow(True)

    # Y-axis formatter
    if meta["yfmt"] == "percent":
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v*100:.1f}%"))
    elif meta["yfmt"] == "ratio":
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.1f}x"))
    elif meta["yfmt"] == "money_millions":
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v:.0f}M"))

    ax.set_xlabel("Fiscal Year", color=TEXT_COLOR, fontsize=11)

    # Give the labels above points some headroom
    if vals:
        lo, hi = min(display_vals), max(display_vals)
        rng = hi - lo if hi != lo else abs(hi) * 0.2 + 1
        ax.set_ylim(lo - 0.15 * rng, hi + 0.3 * rng)

    plt.tight_layout()
    fig.savefig(out_path, facecolor=BG_COLOR, bbox_inches="tight", pad_inches=0.1, dpi=100)
    plt.close(fig)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try a few common font locations; fall back to default."""
    candidates = []
    if bold:
        candidates += [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    candidates += [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def composite(template_path: Path, meta: dict, out_path: Path):
    """Render chart, composite over template, write header text."""
    # Render chart to a bytes buffer
    tmp_chart = OUT_DIR / f".tmp_{template_path.stem}.png"
    render_chart(meta, tmp_chart)

    # Load template and resize chart to fit drop zone
    template = Image.open(template_path).convert("RGBA")
    chart = Image.open(tmp_chart).convert("RGBA")

    # Resize chart to fit drop zone while preserving aspect
    chart.thumbnail((DROP_W, DROP_H), Image.LANCZOS)

    # Center in drop zone
    cw, ch = chart.size
    paste_x = DROP_X + (DROP_W - cw) // 2
    paste_y = DROP_Y + (DROP_H - ch) // 2

    # Draw a solid background rectangle to cover the template's placeholder text
    draw = ImageDraw.Draw(template)
    draw.rectangle((DROP_X, DROP_Y, DROP_X + DROP_W, DROP_Y + DROP_H), fill=BG_COLOR)

    template.paste(chart, (paste_x, paste_y), chart)

    # Replace header text — cover the "City Name, State/Province" with
    # a filled rectangle matching the template's bar, then draw our text.
    # The template's dark-teal header color is close to BG_COLOR.
    draw.rectangle(HEADER_BOX, fill=BG_COLOR)
    font = load_font(42, bold=True)
    draw.text((HEADER_BOX[0] + 20, HEADER_BOX[1] + 10), "Oceanside, California",
              fill=TEXT_COLOR, font=font)

    template.convert("RGB").save(out_path, format="PNG")
    tmp_chart.unlink(missing_ok=True)
    print(f"wrote {out_path.name}")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for template_name, meta in METRICS.items():
        tp = TEMPLATE_DIR / template_name
        if not tp.exists():
            print(f"MISSING: {tp}")
            continue
        out = OUT_DIR / template_name
        composite(tp, meta, out)


if __name__ == "__main__":
    main()
