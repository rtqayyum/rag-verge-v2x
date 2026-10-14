"""Run paired policy experiments for one generated Dubai OMNeT++ scenario."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
import hashlib
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


HERE = Path(__file__).resolve().parent
POLICIES = ("Nearest", "Earliest", "Risk", "Replicate", "Verge")
CONDITIONS = {"nominal": "", "burst": "Burst", "failure": "Failure"}
METRICS = {
    "offeredCritical", "offeredOrdinary", "successCritical", "successOrdinary",
    "lateCritical", "lateOrdinary", "unanswered", "responseCount", "replicatedTasks",
    "vergeShieldFallbacks", "vergeSafeReplications", "ragOverloadFallbacks", "crossedCellWhilePending",
    "handoverEvents", "totalResponseLatency", "totalObservedQueueDelay",
    "maxObservedQueueDelay", "meanDecisionTimeUs",
}


def read_scalars(path: Path) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for line in path.read_text().splitlines():
        if not line.startswith("scalar V2XNetwork."):
            continue
        _, module, metric, value, *_ = line.split()
        if ".ue[" in module and module.endswith(".app[0]") and (
            metric in METRICS or metric.startswith("selectedServer") or metric.startswith("reliabilityServer")
        ):
            totals[metric] += float(value)
        elif ".edge[" in module and module.endswith(".app[0]") and metric in {
            "tasksReceived", "tasksDroppedFailure", "resultsSent", "totalQueueDelay",
            "maxQueueDelay", "serviceWorkUnits", "estimatedBusyFraction"
        }:
            totals[metric] += float(value)
    return dict(totals)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values.sort()
    index = (len(values) - 1) * fraction
    lower, upper = int(index), min(int(index) + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def read_vector_percentiles(path: Path) -> dict[str, float | None]:
    """Read only the two retained KPI vectors before raw OMNeT++ files are pruned."""
    names: dict[str, str] = {}
    samples: dict[str, list[float]] = {"responseLatency": [], "observedQueueDelay": []}
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == "vector":
                names[parts[1]] = parts[3]
            elif len(parts) >= 4 and parts[0] in names and names[parts[0]] in samples:
                samples[names[parts[0]]].append(float(parts[-1]))
    return {
        "p50ResponseLatency": percentile(samples["responseLatency"], .50),
        "p95ResponseLatency": percentile(samples["responseLatency"], .95),
        "p99ResponseLatency": percentile(samples["responseLatency"], .99),
        "p95ObservedQueueDelay": percentile(samples["observedQueueDelay"], .95),
    }


def write_checkpoint(path: Path, ini: Path, prefix: str, rows: list[dict]) -> None:
    """Atomically persist completed paired runs, so an interrupted study resumes safely."""
    payload = {
        "ini": str(ini.relative_to(HERE)),
        "iniSha256": hashlib.sha256(ini.read_bytes()).hexdigest(),
        "prefix": prefix,
        "rows": rows,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)
    with path.with_suffix(".csv").open("w", newline="") as stream:
        fieldnames = sorted(set().union(*(row.keys() for row in rows))) if rows else []
        if fieldnames:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ini", type=Path, required=True)
    parser.add_argument("--prefix", required=True, help="Scenario name supplied to prepare_dubai_ini.py")
    parser.add_argument("--seeds", type=int, default=5, choices=range(1, 21))
    parser.add_argument("--conditions", nargs="*", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--progress-total", type=int, default=0,
                        help="Total simulations in the enclosing study (enables ETA display).")
    parser.add_argument("--progress-offset", type=int, default=0,
                        help="Completed simulations before this scenario.")
    parser.add_argument("--resume", action="store_true",
                        help="Reuse only rows checkpointed with the identical generated INI.")
    parser.add_argument("--retain-raw", action="store_true",
                        help="Keep large OMNeT++ .sca/.vec/.vci files after their KPIs are extracted.")
    args = parser.parse_args()
    ini = args.ini.resolve()
    if not ini.is_file():
        parser.error(f"INI file not found: {ini}")
    environment = os.environ.copy()
    environment["V2X_INI"] = str(ini)
    output = ini.parent / f"{args.prefix}_results.json"
    rows: list[dict] = []
    completed_keys: set[tuple[str, int, str]] = set()
    if args.resume and output.is_file():
        previous = json.loads(output.read_text())
        ini_hash = hashlib.sha256(ini.read_bytes()).hexdigest()
        if previous.get("iniSha256") != ini_hash:
            raise RuntimeError(
                f"Cannot resume {output.name}: its generated INI differs from this run. "
                "Use a distinct study tag so results are never mixed."
            )
        rows = previous.get("rows", [])
        completed_keys = {(row["condition"], row["seed"], row["policy"]) for row in rows}
        print(f"Resuming {args.prefix}: {len(rows)} completed policy/seed runs.", flush=True)
    logs = ini.parent / "logs"
    logs.mkdir(exist_ok=True)
    start = time.perf_counter()
    run_number = 0
    for condition in args.conditions:
        for seed in range(args.seeds):
            paired = None
            for policy in POLICIES:
                policy_key = policy.lower()
                config = f"{args.prefix}{policy}{CONDITIONS[condition]}"
                if (condition, seed, policy_key) in completed_keys:
                    prior = next(row for row in rows if (row["condition"], row["seed"], row["policy"])
                                 == (condition, seed, policy_key))
                    offered = prior.get("offeredCritical", 0), prior.get("offeredOrdinary", 0)
                    if paired is None:
                        paired = offered
                    elif paired != offered:
                        raise RuntimeError(f"Unpaired checkpointed workload for {condition} seed {seed}")
                    continue
                result = subprocess.run(["bash", str(HERE / "run.sh"), config, str(seed)],
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env=environment)
                (logs / f"{config}-{seed}.log").write_text(result.stdout)
                if result.returncode:
                    raise RuntimeError(f"{config} seed {seed} failed; inspect {logs / f'{config}-{seed}.log'}")
                scalar_path = ini.parent / "results" / f"{config}-{seed}.sca"
                vector_path = ini.parent / "results" / f"{config}-{seed}.vec"
                values = read_scalars(scalar_path)
                offered = values.get("offeredCritical", 0), values.get("offeredOrdinary", 0)
                if paired is None:
                    paired = offered
                elif paired != offered:
                    raise RuntimeError(f"Unpaired workload for {condition} seed {seed}: {paired} versus {offered}")
                row = {"condition": condition, "seed": seed, "policy": policy_key,
                       "config": config, "scalarFile": str(scalar_path.relative_to(HERE)),
                       "vectorFile": str(vector_path.relative_to(HERE)), **values,
                       **read_vector_percentiles(vector_path)}
                row["criticalCompletionRate"] = values.get("successCritical", 0) / offered[0] if offered[0] else 0
                row["ordinaryCompletionRate"] = values.get("successOrdinary", 0) / offered[1] if offered[1] else 0
                row["meanResponseLatency"] = values.get("totalResponseLatency", 0) / values.get("responseCount", 1)
                row["meanObservedQueueDelay"] = values.get("totalObservedQueueDelay", 0) / values.get("responseCount", 1)
                row["meanServerQueueDelay"] = values.get("totalQueueDelay", 0) / values.get("resultsSent", 1)
                rows.append(row)
                completed_keys.add((condition, seed, policy_key))
                write_checkpoint(output, ini, args.prefix, rows)
                if not args.retain_raw:
                    for raw in (scalar_path, vector_path, vector_path.with_suffix(".vci")):
                        raw.unlink(missing_ok=True)
                run_number += 1
                if args.progress_total:
                    complete = args.progress_offset + run_number
                    elapsed = time.perf_counter() - start
                    # Estimate from this scenario plus all already-completed work represented by offset.
                    rate = run_number / elapsed if elapsed else 0.0
                    remaining = (args.progress_total - complete) / rate if rate else 0.0
                    eta = time.strftime("%H:%M:%S", time.gmtime(max(0, remaining)))
                    print(f"[overall {complete}/{args.progress_total} | {100 * complete / args.progress_total:5.1f}%"
                          f" | ETA {eta}] {args.prefix} {condition} seed={seed} {policy}"
                          f" critical={row['criticalCompletionRate']:.3f}", flush=True)
                else:
                    print(condition, seed, policy, f"critical={row['criticalCompletionRate']:.3f}", flush=True)
    write_checkpoint(output, ini, args.prefix, rows)
    for condition in args.conditions:
        for policy in POLICIES:
            values = [row["criticalCompletionRate"] for row in rows
                      if row["condition"] == condition and row["policy"] == policy.lower()]
            print(condition, policy, f"{mean(values):.3f}",
                  f"({stdev(values):.3f})" if len(values) > 1 else "")
    print(output)


if __name__ == "__main__":
    main()
