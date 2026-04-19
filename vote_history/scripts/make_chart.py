"""Generate a summary chart showing the voting record by member."""
import csv
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "votes.csv"

MEMBERS = ["SANCHEZ", "KEIM", "JOYCE", "ROBINSON", "WEISS", "FIGUEROA"]
LABEL = {
    "SANCHEZ": "Sanchez",
    "KEIM": "Keim",
    "JOYCE": "Joyce",
    "ROBINSON": "Robinson",
    "WEISS": "Weiss",
    "FIGUEROA": "Figueroa",
}
COLORS = {
    "Yes": "#4C9F4A",
    "No": "#D64545",
    "Abstain": "#E0A145",
    "Absent": "#B0B0B0",
    "NotOnCouncil": "#E8E8E8",
}
STATES = ["Yes", "No", "Abstain", "Absent", "NotOnCouncil"]


def main():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    total = len(rows)

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13, 5),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    # Stacked bar per member
    counts = {m: Counter(r[m] for r in rows) for m in MEMBERS}
    x = list(range(len(MEMBERS)))
    bottom = [0] * len(MEMBERS)
    for state in STATES:
        vals = [counts[m].get(state, 0) for m in MEMBERS]
        ax1.bar(x, vals, bottom=bottom, color=COLORS[state],
                edgecolor="white", linewidth=0.5, label=state)
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax1.set_xticks(x)
    ax1.set_xticklabels([LABEL[m] for m in MEMBERS], fontsize=10)
    ax1.set_ylabel(f"Vote records (of {total} total)")
    ax1.set_title("Oceanside City Council voting record, Dec 2022 – Apr 2026",
                  fontsize=11, pad=12)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # Annotate Yes/No tallies on each bar
    for i, m in enumerate(MEMBERS):
        yes = counts[m].get("Yes", 0)
        no = counts[m].get("No", 0)
        ax1.text(i, yes / 2, f"{yes}", ha="center", va="center",
                 color="white", fontsize=10, fontweight="bold")
        if no > 0:
            ax1.text(i, yes + no / 2, f"{no}", ha="center", va="center",
                     color="white", fontsize=9, fontweight="bold")

    handles = [mpatches.Patch(color=COLORS[s], label=s) for s in STATES]
    ax1.legend(handles=handles, loc="upper right", fontsize=9, frameon=False)

    # Right panel: motion outcomes
    outcomes = Counter(r["outcome"] for r in rows)
    split_votes = sum(1 for r in rows if int(r["vote_count_against"]) > 0)
    unanimous = total - split_votes

    ax2.barh(["Unanimous", "Split\n(≥1 No)"], [unanimous, split_votes],
             color=["#4C9F4A", "#D64545"])
    ax2.set_xlabel("Motions")
    ax2.set_title(f"{total} motions total", fontsize=11, pad=12)
    for i, v in enumerate([unanimous, split_votes]):
        ax2.text(v + total * 0.01, i, f" {v}", va="center", fontsize=10)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.set_xlim(0, total * 1.15)

    plt.tight_layout()
    out = ROOT / "voting_record_chart.png"
    plt.savefig(out, dpi=130, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
