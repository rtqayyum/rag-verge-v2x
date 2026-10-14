"""Enrich Dubai experiment results with vector percentiles and create KPI plots."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (index - lower)


def vector_samples(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    names: dict[str, str] = {}
    samples: dict[str, list[float]] = defaultdict(list)
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "vector" and len(parts) >= 4:
            names[parts[1]] = parts[3]
        elif parts[0] in names and len(parts) >= 4:
            name = names[parts[0]]
            if name in {"responseLatency", "observedQueueDelay"}:
                samples[name].append(float(parts[-1]))
    return samples


def enrich(rows: list[dict]) -> list[dict]:
    for row in rows:
        if row.get("p95ResponseLatency") is not None:
            match = re.search(r"V(\d+)R(\d+)", row.get("config", ""))
            if match:
                row["vehicles"], row["rsus"] = map(int, match.groups())
            continue
        vector_path = Path(row["vectorFile"])
        if not vector_path.is_absolute():
            vector_path = HERE / vector_path
        samples = vector_samples(vector_path)
        latency, queue = samples.get("responseLatency", []), samples.get("observedQueueDelay", [])
        row["p50ResponseLatency"] = percentile(latency, .50)
        row["p95ResponseLatency"] = percentile(latency, .95)
        row["p99ResponseLatency"] = percentile(latency, .99)
        row["p95ObservedQueueDelay"] = percentile(queue, .95)
        match = re.search(r"V(\d+)R(\d+)", row.get("config", ""))
        if match:
            row["vehicles"], row["rsus"] = map(int, match.groups())
    return rows


def grouped_plot(rows: list[dict], metric: str, title: str, output: Path) -> None:
    policies = sorted({row["policy"] for row in rows})
    conditions = [item for item in ("nominal", "burst", "failure") if any(row["condition"] == item for row in rows)]
    if not policies or not conditions:
        return
    width = .8 / len(policies)
    figure, axis = plt.subplots(figsize=(9, 5))
    for index, policy in enumerate(policies):
        values = []
        for condition in conditions:
            group = [row[metric] for row in rows if row["policy"] == policy and row["condition"] == condition
                     and row.get(metric) is not None]
            values.append(mean(group) if group else float("nan"))
        axis.bar([position + (index - (len(policies) - 1) / 2) * width for position in range(len(conditions))],
                 values, width=width, label=policy)
    axis.set_xticks(range(len(conditions)), conditions)
    axis.set_ylabel(metric)
    axis.set_title(title)
    axis.legend(ncol=min(5, len(policies)))
    axis.grid(axis="y", alpha=.25)
    figure.tight_layout()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def scaling_plot(rows: list[dict], variable: str, output: Path) -> None:
    if not all(variable in row for row in rows):
        return
    figure, axis = plt.subplots(figsize=(9, 5))
    for policy in sorted({row["policy"] for row in rows}):
        group = defaultdict(list)
        for row in rows:
            if row["policy"] == policy and row["condition"] == "failure":
                group[row[variable]].append(row["criticalCompletionRate"])
        if group:
            x = sorted(group)
            axis.plot(x, [mean(group[item]) for item in x], marker="o", label=policy)
    axis.set_xlabel(variable)
    axis.set_ylabel("critical completion rate under failure")
    axis.set_title(f"Failure scaling by {variable}")
    axis.legend(ncol=2)
    axis.grid(alpha=.25)
    figure.tight_layout()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", type=Path, help="One or more *_results.json files")
    parser.add_argument("--output", type=Path, default=Path("research/omnet/v2x_model/analysis"))
    args = parser.parse_args()
    rows = []
    for path in args.results:
        rows.extend(json.loads(path.read_text())["rows"])
    rows = enrich(rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "enriched_results.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = sorted(set().union(*(row.keys() for row in rows)))
    with (args.output / "enriched_results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    figures = {
        "01_critical_completion.png": ("criticalCompletionRate", "Critical deadline completion"),
        "02_ordinary_completion.png": ("ordinaryCompletionRate", "Ordinary-task completion"),
        "03_mean_latency.png": ("meanResponseLatency", "Mean end-to-end latency"),
        "04_p95_latency.png": ("p95ResponseLatency", "p95 end-to-end latency"),
        "05_p99_latency.png": ("p99ResponseLatency", "p99 end-to-end latency"),
        "06_mean_queue_delay.png": ("meanObservedQueueDelay", "Mean observed queue delay"),
        "07_p95_queue_delay.png": ("p95ObservedQueueDelay", "p95 observed queue delay"),
        "08_replication_overhead.png": ("replicatedTasks", "Replication overhead"),
        "09_edge_failure_drops.png": ("tasksDroppedFailure", "Requests dropped during edge failure"),
        "10_handover_events.png": ("handoverEvents", "Handover events"),
        "11_shield_fallbacks.png": ("vergeShieldFallbacks", "VERGE safety-shield fallbacks"),
        "12_rag_overload_fallbacks.png": ("ragOverloadFallbacks", "RAG overload-policy selections"),
        "13_decision_time.png": ("meanDecisionTimeUs", "Mean scheduler decision time (microseconds)"),
    }
    for filename, (metric, title) in figures.items():
        if any(row.get(metric) is not None for row in rows):
            grouped_plot(rows, metric, title, args.output / filename)
    scaling_plot(rows, "rsus", args.output / "14_rsu_scaling_failure.png")
    scaling_plot(rows, "vehicles", args.output / "15_vehicle_scaling_failure.png")
    print(args.output)


if __name__ == "__main__":
    main()
