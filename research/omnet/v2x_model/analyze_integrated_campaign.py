"""Summarize an integrated campaign and write publication-ready figures.

The script never mixes manifests: it reads one held-out JSON file and writes
tables/figures beside it. Metrics are paired by workload, policy, and seed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    data = json.loads(args.result.read_text())
    out = args.out or args.result.with_name(args.result.stem + "_figures")
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(data["rows"])
    frame.to_csv(out / "heldout_rows.csv", index=False)
    metrics = {
        "criticalCompletionRate": "Critical completion",
        "ordinaryCompletionRate": "Ordinary completion",
        "criticalRejectionRate": "Critical rejection",
        "responseCoverage": "Response coverage",
        "meanResponseLatencyS": "Mean response latency (s)",
        "meanStateAgeS": "Mean report age (s)",
        "signalingBytesPerS": "Signaling payload (B/s)",
        "admittedWorkUnits": "Admitted work",
        "offeredWorkUnits": "Offered work",
    }
    frame["cell"] = (frame["taskIntervalS"].map(lambda x: f"I{x:g}") +
                      "/P" + frame["reportPeriodS"].map(lambda x: f"{x:g}"))
    summary = frame.groupby(["cell", "method"], as_index=False)[list(metrics)].mean()
    summary.to_csv(out / "summary_by_cell.csv", index=False)
    for column, label in metrics.items():
        pivot = summary.pivot(index="cell", columns="method", values=column)
        ax = pivot.plot(kind="bar", figsize=(9, 4.5), width=.82,
                        color={"ReportedEarliest": "#0072B2", "Power2": "#D55E00",
                               "DahlinAge": "#009E73", "OracleDiagnostic": "#777777",
                               "RAG-retrieval": "#7A3DB8", "LLM-no-retrieval": "#CC79A7",
                               "Random-search": "#E69F00", "Kernel-surrogate": "#56B4E9"})
        ax.set_xlabel("Workload cell")
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=.25)
        ax.legend(ncol=4, fontsize=7, frameon=False)
        fig = ax.get_figure(); fig.tight_layout()
        fig.savefig(out / f"{column}.pdf", bbox_inches="tight")
        fig.savefig(out / f"{column}.png", dpi=240, bbox_inches="tight")
        plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
