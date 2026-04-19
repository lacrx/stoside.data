"""Chart of every failed motion (motion proposed, seconded, then voted down)."""
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

# Color key: 0=NotOnCouncil, 1=Absent, 2=Abstain, 3=Yes (supporter), 4=No (blocker)
COLORS = ["#F2F2F2", "#CCCCCC", "#E0A145", "#4C9F4A", "#D64545"]
STATE_TO_CODE = {
    "NotOnCouncil": 0, "Absent": 1, "Abstain": 2,
    "Yes": 3, "No": 4, "Unknown": 0,
}


def short_label(r):
    """Build a readable one-liner. Prefer motion_summary; fall back to title."""
    m = (r.get("motion_summary") or "").strip()
    t = (r.get("item_title") or "").strip()
    # If motion_summary is a name only (mover like "Keim"), use item_title
    if not m or len(m) < 12 or m.lower() in ("motion", "approve consent calendar"):
        label = t
    else:
        label = m
    for pfx in ("Staff recommends that the City Council ", "Staff recommends ",
                "City Council: ", "MOTION TO ", "Motion to ", "Request by "):
        if label.startswith(pfx):
            label = label[len(pfx):]
            break
    label = label[:85]
    date_mover = f"{r['meeting_date']}  #{r['item_number']:>2}  by {r['mover'].title()}/{r['seconder'].title() or '—'}"
    return date_mover, label


def main():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    failed = [r for r in rows if r["outcome"] in
              ("FAILED", "DEFEATED", "DENIED", "REJECTED", "WITHDRAWN")]
    failed.sort(key=lambda r: (r["meeting_date"], int(r["item_number"])))
    n = len(failed)

    grid = np.zeros((n, len(MEMBERS)), dtype=int)
    for i, r in enumerate(failed):
        for j, m in enumerate(MEMBERS):
            grid[i, j] = STATE_TO_CODE.get(r[m], 0)

    fig, ax = plt.subplots(figsize=(14, max(7, n * 0.38)))
    cmap = ListedColormap(COLORS)
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=4, aspect="auto")

    ax.set_xticks(range(len(MEMBERS)))
    ax.set_xticklabels([LABEL[m] for m in MEMBERS], fontsize=11)
    ax.xaxis.tick_top()

    labels_left = []
    for r in failed:
        date_mover, topic = short_label(r)
        labels_left.append(f"{date_mover}\n  {topic}")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels_left, fontsize=9, family="monospace")

    # Minor gridlines between cells
    ax.set_xticks(np.arange(-.5, len(MEMBERS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", length=0)

    # Vote tally on the far right of each row
    for i, r in enumerate(failed):
        ax.text(len(MEMBERS) - 0.35, i,
                f"  {r['vote_count_for']}–{r['vote_count_against']}",
                va="center", ha="left", fontsize=10, fontweight="bold",
                family="monospace")

    ax.set_title(
        f"Failed motions on the Oceanside City Council, Dec 2022 – Apr 2026  "
        f"({n} of 1,232 motions)",
        fontsize=13, pad=20, loc="left",
    )

    legend_handles = [
        mpatches.Patch(color=COLORS[3], label="Voted for (but failed)"),
        mpatches.Patch(color=COLORS[4], label="Voted against"),
        mpatches.Patch(color=COLORS[2], label="Abstain"),
        mpatches.Patch(color=COLORS[1], label="Absent"),
        mpatches.Patch(color=COLORS[0], label="Not on council"),
    ]
    ax.legend(
        handles=legend_handles, loc="lower center",
        bbox_to_anchor=(0.5, -0.08 - 0.5 / max(n, 1)), ncol=5,
        frameon=False, fontsize=10,
    )

    plt.tight_layout()
    out = ROOT / "failed_motions_chart.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
