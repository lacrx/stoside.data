"""Chart showing every split vote (≥1 No) with who voted which way."""
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "votes.csv"

MEMBERS = ["SANCHEZ", "KEIM", "JOYCE", "ROBINSON", "WEISS", "FIGUEROA"]
LABEL = {m: m.title() for m in MEMBERS}

# Color key: 0=NotOnCouncil, 1=Absent, 2=Abstain, 3=Yes, 4=No
COLORS = ["#F2F2F2", "#CCCCCC", "#E0A145", "#4C9F4A", "#D64545"]
STATE_TO_CODE = {
    "NotOnCouncil": 0, "Absent": 1, "Abstain": 2,
    "Yes": 3, "No": 4, "Unknown": 0,
}


def short_title(r):
    """Build a short, readable label for the vote."""
    t = (r.get("motion_summary") or "").strip()
    if not t or t.lower() in ("motion", "approve consent calendar"):
        t = (r.get("item_title") or "").strip()
    # Strip boilerplate prefixes
    for pfx in ("Staff recommends that the City Council ",
                "Staff recommends ",
                "City Council: ",
                "City Council/Harbor/CDC/OPFA: ",
                "Motion to ", "MOTION TO ",
                "Approve ", "Approval of "):
        if t.startswith(pfx):
            t = t[len(pfx):]
            break
    t = t[:75]
    return f"{r['meeting_date']}  #{r['item_number']:>2}  {t}"


def main():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    splits = [r for r in rows if int(r["vote_count_against"]) > 0]
    splits.sort(key=lambda r: (r["meeting_date"], int(r["item_number"])))
    n = len(splits)

    # Build the matrix
    grid = np.zeros((n, len(MEMBERS)), dtype=int)
    for i, r in enumerate(splits):
        for j, m in enumerate(MEMBERS):
            grid[i, j] = STATE_TO_CODE.get(r[m], 0)

    fig, ax = plt.subplots(figsize=(12, max(10, n * 0.22)))
    cmap = ListedColormap(COLORS)
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=4, aspect="auto")

    # X axis = members
    ax.set_xticks(range(len(MEMBERS)))
    ax.set_xticklabels([LABEL[m] for m in MEMBERS], fontsize=10)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")

    # Y axis = short descriptions
    ax.set_yticks(range(n))
    ax.set_yticklabels([short_title(r) for r in splits], fontsize=8,
                       family="monospace")

    # Thin gridlines between cells
    ax.set_xticks(np.arange(-.5, len(MEMBERS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", length=0)

    # Annotate "No" cells with the count summary on the far right
    for i, r in enumerate(splits):
        cf = r["vote_count_for"]
        ca = r["vote_count_against"]
        ax.text(len(MEMBERS) - 0.4, i, f"  {cf}–{ca}",
                va="center", ha="left", fontsize=8, family="monospace")

    ax.set_title(
        f"Every split vote on the Oceanside City Council, Dec 2022 – Apr 2026  "
        f"({n} of 1,227 motions)",
        fontsize=12, pad=18, loc="left",
    )

    # Legend
    legend_handles = [
        mpatches.Patch(color=COLORS[3], label="Yes"),
        mpatches.Patch(color=COLORS[4], label="No"),
        mpatches.Patch(color=COLORS[2], label="Abstain"),
        mpatches.Patch(color=COLORS[1], label="Absent"),
        mpatches.Patch(color=COLORS[0], label="Not on council"),
    ]
    ax.legend(
        handles=legend_handles, loc="lower center",
        bbox_to_anchor=(0.5, -0.04), ncol=5, frameon=False, fontsize=9,
    )

    plt.tight_layout()
    out = ROOT / "dissent_chart.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
