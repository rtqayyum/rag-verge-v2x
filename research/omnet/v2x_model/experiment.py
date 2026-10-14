"""Run paired Simu5G task-scheduling experiments and summarize scalar output."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


HERE = Path(__file__).resolve().parent
CONFIGS = {
    "nominal": {"nearest": "Nearest", "earliest": "Earliest", "risk": "Risk", "replicate": "Replicate", "verge": "Verge"},
    "burst": {"nearest": "NearestBurst", "earliest": "EarliestBurst", "risk": "RiskBurst", "replicate": "ReplicateBurst", "verge": "VergeBurst"},
    "failure": {"nearest": "NearestFailure", "earliest": "EarliestFailure", "risk": "RiskFailure", "replicate": "ReplicateFailure", "verge": "VergeFailure"},
}
METRICS = (
    "offeredCritical", "offeredOrdinary", "successCritical", "successOrdinary",
    "lateCritical", "lateOrdinary", "unanswered", "responseCount",
    "crossedCellWhilePending", "selectedEdge1", "selectedEdge2", "replicatedTasks",
    "vergeShieldFallbacks", "vergeSafeReplications",
)


def read_scalars(path: Path) -> dict[str, float]:
    totals = defaultdict(float)
    for line in path.read_text().splitlines():
        if not line.startswith("scalar V2XNetwork."):
            continue
        _, module, name, value, *_ = line.split()
        if ".ue[" in module and module.endswith(".app[0]") and name in METRICS:
            totals[name] += float(value)
        elif ".edge" in module and module.endswith(".app[0]") and name in (
            "tasksReceived", "tasksDroppedFailure", "resultsSent"
        ):
            totals[name] += float(value)
    return dict(totals)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5,
                        help="Number of paired repetitions to run (1--20).")
    parser.add_argument("--conditions", nargs="*", choices=CONFIGS, default=list(CONFIGS))
    args = parser.parse_args()
    if not 1 <= args.seeds <= 20:
        parser.error("--seeds must be between 1 and 20; update tasks.ini to extend the run set")
    rows = []
    logs = HERE / "logs"
    logs.mkdir(exist_ok=True)
    for condition in args.conditions:
        for seed in range(args.seeds):
            paired_offered = None
            for policy, config in CONFIGS[condition].items():
                result = subprocess.run(
                    ["bash", str(HERE / "run.sh"), config, str(seed)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
                (logs / f"{config}-{seed}.log").write_text(result.stdout)
                if result.returncode:
                    raise RuntimeError(f"{config} seed {seed} failed; see {logs / f'{config}-{seed}.log'}")
                scalar = HERE / "scenario" / "results" / f"{config}-{seed}.sca"
                values = read_scalars(scalar)
                offered = (values.get("offeredCritical", 0), values.get("offeredOrdinary", 0))
                if paired_offered is None:
                    paired_offered = offered
                elif paired_offered != offered:
                    raise RuntimeError(f"Unpaired task stream in {condition} seed {seed}: {paired_offered} vs {offered}")
                expected_requests = sum(offered) + values.get("replicatedTasks", 0)
                not_arrived = expected_requests - values.get("tasksReceived", 0)
                if not_arrived < 0 or not_arrived > 0.05 * sum(offered):
                    raise RuntimeError(f"Implausible request delivery in {config} seed {seed}: {values}")
                row = {"condition": condition, "seed": seed, "policy": policy, **values}
                row["requestsNotArrivedByHorizon"] = not_arrived
                row["criticalCompletionRate"] = values.get("successCritical", 0) / offered[0] if offered[0] else 0
                row["ordinaryCompletionRate"] = values.get("successOrdinary", 0) / offered[1] if offered[1] else 0
                rows.append(row)
                print(condition, seed, policy, round(row["criticalCompletionRate"], 3),
                      round(row["ordinaryCompletionRate"], 3), flush=True)
    output = HERE / "experiment_results.json"
    output.write_text(json.dumps({
        "method": "SUMO trajectories plus packet-level Simu5G, abstract edge compute queues",
        "versions": {"omnetpp": "6.4.0", "inet": "4.7.0", "simu5g": "1.8.0", "sumo": "1.28.0"},
        "mobility_trace": "scenario/sumo.movements, SUMO seed 1",
        "rows": rows,
    }, indent=2) + "\n")
    with (HERE / "experiment_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        writer.writeheader()
        writer.writerows(rows)
    print("Summary means (sample SD):")
    for condition in args.conditions:
        for policy in CONFIGS[condition]:
            group = [r["criticalCompletionRate"] for r in rows if r["condition"] == condition and r["policy"] == policy]
            print(condition, policy, f"{mean(group):.3f}", f"({stdev(group):.3f})" if len(group) > 1 else "")
    print(output)


if __name__ == "__main__":
    main()
