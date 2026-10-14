"""Summarize leakage-aware RAG portfolio evaluations into paper-ready tables."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    rows = []
    for item in manifest["completed"]:
        result_path = Path(item["result"])
        if not result_path.is_absolute():
            result_path = HERE / result_path
        payload = json.loads(result_path.read_text())
        candidate = payload["heldOutSummary"]
        for policy, static in payload["staticHeldOutSummary"].items():
            rows.append({**item, "policy": "ragverge" if policy == "verge" else policy,
                         "comparator": policy, "criticalCompletionRate": candidate["criticalCompletionRate"],
                         "meanResponseLatency": candidate["meanResponseLatency"],
                         "replicatedTasks": candidate["replicatedTasks"],
                         "ragOverloadFallbacks": candidate.get("ragOverloadFallbacks", 0),
                         "deltaCompletionVsComparator": payload["pairedDeltaVsStatic"][policy]["criticalCompletionRate"],
                         "deltaLatencyVsComparator": payload["pairedDeltaVsStatic"][policy]["meanResponseLatency"],
                         "comparatorCompletionRate": static["criticalCompletionRate"],
                         "comparatorLatency": static["meanResponseLatency"]})
    args.output.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with (args.output / "rag_portfolio_paired_summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    (args.output / "rag_portfolio_paired_summary.json").write_text(json.dumps(rows, indent=2) + "\n")

    for comparator, metric, label, filename in [
        ("verge", "deltaCompletionVsComparator", "RAG-VERGE minus static VERGE completion", "01_delta_completion_vs_verge.png"),
        ("verge", "deltaLatencyVsComparator", "RAG-VERGE minus static VERGE latency (s)", "02_delta_latency_vs_verge.png"),
        ("earliest", "deltaCompletionVsComparator", "RAG-VERGE minus Earliest completion", "03_delta_completion_vs_earliest.png"),
    ]:
        selected = [row for row in rows if row["comparator"] == comparator]
        if not selected:
            continue
        labels = [f"V{x['vehicles']}/R{x['rsus']}\n{x['condition']}" for x in selected]
        figure, axis = plt.subplots(figsize=(max(8, len(labels) * .9), 5))
        axis.bar(range(len(selected)), [x[metric] for x in selected])
        axis.axhline(0, color="black", linewidth=.8)
        axis.set_xticks(range(len(selected)), labels, rotation=45, ha="right")
        axis.set_ylabel(label); axis.grid(axis="y", alpha=.25); figure.tight_layout()
        figure.savefig(args.output / filename, dpi=180); plt.close(figure)
    print(args.output)


if __name__ == "__main__":
    main()
