"""Resumable packet-telemetry gate: matched mobility, task streams, and seeds.

This is a screening study, not a confirmatory journal experiment. It generates
an immutable SUMO trace, a new OMNeT++ INI, runs paired policies, and saves
per-run metrics before deleting raw simulator files unless requested.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from generate_dubai import generate
from prepare_stale_ini import POLICIES, label_ms, prepare


HERE = Path(__file__).resolve().parent
UE_METRICS = {
    "offeredCritical", "offeredOrdinary", "totalOfferedWorkUnits",
    "successCritical", "successOrdinary", "lateCritical", "lateOrdinary",
    "unanswered", "responseCount", "totalResponseLatency", "stateReportsReceived",
    "stateReportsOutOfOrder", "stateDecisionsWithReport",
    "stateDecisionsWithoutReport", "stateSubscriptionsSent", "stateBytesReceived",
    "stateSubscriptionBytesSent",
}
EDGE_METRICS = {
    "tasksReceived", "tasksDroppedFailure", "resultsSent", "serviceWorkUnits",
    "totalQueueDelay", "stateReportsSent", "stateBytesSent",
    "stateSubscriptionsReceived",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hash() -> str:
    digest = hashlib.sha256()
    for name in ("src/TaskApps.cc", "src/TaskPacket.msg", "src/v2x/TaskClient.ned",
                 "src/v2x/TaskServer.ned", "src/v2x/V2XNetwork.ned",
                 "generate_dubai.py", "prepare_dubai_ini.py", "prepare_stale_ini.py",
                 "run_stale_screen.py"):
        digest.update(name.encode())
        digest.update((HERE / name).read_bytes())
    return digest.hexdigest()


def scalar_metrics(path: Path) -> dict[str, float]:
    result: defaultdict[str, float] = defaultdict(float)
    seen: set[str] = set()
    for line in path.open():
        if not line.startswith("scalar V2XNetwork."):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        _, module, metric, value = parts[:4]
        if (".ue[" in module and metric in UE_METRICS) or (
            ".edge[" in module and metric in EDGE_METRICS
        ):
            result[metric] += float(value)
            seen.add(metric)
    missing = (UE_METRICS | EDGE_METRICS) - seen
    if missing:
        raise RuntimeError(f"Missing named scalars in {path.name}: {sorted(missing)}")
    return dict(result)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values.sort()
    index = (len(values) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def vector_metrics(path: Path) -> dict[str, float | None]:
    names: dict[str, str] = {}
    samples: dict[str, list[float]] = {"responseLatency": [], "stateAgeAtDecision": []}
    for line in path.open():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "vector":
            names[parts[1]] = parts[3]
        elif len(parts) >= 4 and parts[0] in names and names[parts[0]] in samples:
            samples[names[parts[0]]].append(float(parts[-1]))
    return {
        "p95ResponseLatency": percentile(samples["responseLatency"], .95),
        "p99ResponseLatency": percentile(samples["responseLatency"], .99),
        "p95StateAgeAtDecision": percentile(samples["stateAgeAtDecision"], .95),
    }


def checkpoint(path: Path, manifest: dict, rows: list[dict]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"manifest": manifest, "rows": rows}, indent=2) + "\n")
    temporary.replace(path)
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", newline="") as stream:
        fields = sorted(set().union(*(row.keys() for row in rows))) if rows else []
        if fields:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def summarize(rows: list[dict], output: Path) -> None:
    groups: defaultdict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["taskIntervalS"], row["reportPeriodS"], row["policy"])].append(row)
    summary: list[dict] = []
    for (interval, period, policy), members in sorted(groups.items()):
        completions = [row["criticalCompletionRate"] for row in members]
        summary.append({
            "taskIntervalS": interval, "reportPeriodS": period, "policy": policy,
            "n": len(members), "meanCriticalCompletion": mean(completions),
            "sdCriticalCompletion": stdev(completions) if len(completions) > 1 else None,
            "meanOrdinaryCompletion": mean(row["ordinaryCompletionRate"] for row in members),
            "meanResponseCoverage": mean(row["responseCoverage"] for row in members),
            "meanOfferedLoadRatio": mean(row["offeredLoadRatio"] for row in members),
            "meanReportAgeS": mean(row["meanStateAgeAtDecisionS"] for row in members),
            "meanSignalingPayloadBytesPerS": mean(row["signalingPayloadBytesPerS"] for row in members),
        })
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]) if summary else [])
        if summary:
            writer.writeheader()
            writer.writerows(summary)
    if len(summary) < 3:
        return
    try:
        cache = output.parent / ".matplotlib-cache"
        cache.mkdir(exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache))
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    colors = {"StaleLeast": "#2563eb", "Power2": "#d97706", "AgeAware": "#059669",
              "FreshPower2": "#7c3aed", "FreshP2NoFreshness": "#9333ea",
              "FreshP2NoCritical": "#be185d"}
    intervals = sorted({row["taskIntervalS"] for row in summary}, reverse=True)
    fig, axes = plt.subplots(1, len(intervals), figsize=(5 * len(intervals), 4), sharey=True)
    if len(intervals) == 1:
        axes = [axes]
    for ax, interval in zip(axes, intervals):
        for policy in POLICIES:
            points = sorted((row for row in summary if row["taskIntervalS"] == interval and
                             row["policy"] == policy), key=lambda row: row["reportPeriodS"])
            if points:
                ax.errorbar([point["reportPeriodS"] for point in points],
                            [point["meanCriticalCompletion"] for point in points],
                            yerr=[point["sdCriticalCompletion"] or 0 for point in points],
                            marker="o", capsize=2, label=policy, color=colors[policy])
        ax.set(xlabel="Report period (s)", title=f"Task interval {interval:g} s", ylim=(0, 1))
        ax.grid(alpha=.25)
    axes[0].set_ylabel("Critical deadline completion")
    axes[-1].legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(output.with_name(output.stem + "_completion.png"), dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, len(intervals), figsize=(5 * len(intervals), 4), sharey=True)
    if len(intervals) == 1:
        axes = [axes]
    for ax, interval in zip(axes, intervals):
        for policy in POLICIES:
            points = [row for row in summary if row["taskIntervalS"] == interval and
                      row["policy"] == policy]
            ax.scatter([point["meanSignalingPayloadBytesPerS"] for point in points],
                       [point["meanCriticalCompletion"] for point in points],
                       label=policy, color=colors[policy])
            for point in points:
                ax.annotate(f"{point['reportPeriodS']:g}s",
                            (point["meanSignalingPayloadBytesPerS"], point["meanCriticalCompletion"]),
                            xytext=(3, 3), textcoords="offset points", fontsize=7)
        ax.set(xlabel="State signaling payload (B/s)",
               title=f"Task interval {interval:g} s", ylim=(0, 1))
        ax.grid(alpha=.25)
    axes[0].set_ylabel("Critical deadline completion")
    axes[-1].legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(output.with_name(output.stem + "_pareto.png"), dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-tag", default="StaleGateV2")
    parser.add_argument("--area", choices=("downtown", "marina", "szr"), default="downtown")
    parser.add_argument("--vehicles", type=int, default=75)
    parser.add_argument("--rsus", type=int, default=4)
    parser.add_argument("--mobility-seed", type=int, default=1)
    parser.add_argument("--scenario", type=Path,
                        help="Reuse an existing immutable activity-aware SUMO trace")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--total-edge-rate", type=float, default=160.0)
    parser.add_argument("--task-intervals", nargs="+", type=float, default=[0.6, 0.3])
    parser.add_argument("--report-periods", nargs="+", type=float, default=[0.1, 0.5, 1.0])
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--smoke", action="store_true",
                        help="Run one load/period and all three packet-state policies, seed 0 only.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retain-raw", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if args.seeds < 1 or args.seeds > 20:
        parser.error("--seeds must be between 1 and 20")
    if args.total_edge_rate <= 0 or args.duration < 20:
        parser.error("edge rate must be positive and duration at least 20 seconds")
    if not args.skip_build:
        subprocess.run(["bash", str(HERE / "build.sh")], check=True)
    scenario = (args.scenario.resolve() if args.scenario else
                generate(args.area, args.vehicles, args.mobility_seed, args.duration,
                         0.5, args.study_tag))
    if not (scenario / "metadata.json").exists():
        raise RuntimeError(f"Scenario metadata not found: {scenario}")
    metadata = json.loads((scenario / "metadata.json").read_text())
    name = f"{args.study_tag}{args.area.title()}V{args.vehicles}R{args.rsus}"
    ini = prepare(scenario, args.rsus, args.total_edge_rate, name,
                  args.task_intervals, args.report_periods)
    if args.smoke:
        intervals = args.task_intervals[:1]
        periods = args.report_periods[1:2] or args.report_periods[:1]
        seeds = range(1)
    else:
        intervals, periods, seeds = args.task_intervals, args.report_periods, range(args.seeds)
    cases = [(interval, period, policy, seed)
             for interval in intervals for period in periods
             for seed in seeds for policy in POLICIES]
    if not args.smoke:
        reference_period = args.report_periods[len(args.report_periods) // 2]
        cases += [(interval, reference_period, "FreshLeast", seed)
                  for interval in intervals for seed in seeds]
    out = ini.with_name(f"{name}_{'smoke' if args.smoke else 'stale_screen'}_results.json")
    manifest = {
        "studyTag": args.study_tag, "area": args.area, "vehicles": args.vehicles,
        "rsus": args.rsus, "mobilitySeed": args.mobility_seed,
        "durationS": args.duration, "totalEdgeRate": args.total_edge_rate,
        "taskIntervalsS": args.task_intervals, "reportPeriodsS": args.report_periods,
        "networkSeeds": args.seeds, "smoke": args.smoke, "iniSha256": sha256(ini),
        "sourceSha256": source_hash(), "traceSha256": metadata["sha256"]["trace"],
        "routesSha256": metadata["sha256"]["routes"],
        "meanActiveVehicles": metadata["mean_active_vehicles"],
        "peakActiveVehicles": metadata["peak_active_vehicles"],
        "description": "Packet-delivered server-state screening; FreshLeast is an unattainable instantaneous-state reference, not an upper bound.",
    }
    rows: list[dict] = []
    if out.exists():
        if not args.resume:
            raise RuntimeError(f"Results already exist: {out}; use --resume or a new study tag")
        previous = json.loads(out.read_text())
        if previous.get("manifest") != manifest:
            raise RuntimeError("Cannot resume: source, INI, inputs, or design changed")
        rows = previous["rows"]
    keys = {(row["taskIntervalS"], row["reportPeriodS"], row["policy"], row["seed"])
            for row in rows}
    expected = len(cases)
    done = sum(case in keys for case in cases)
    print(f"Active vehicles mean={metadata['mean_active_vehicles']:.1f}, "
          f"peak={metadata['peak_active_vehicles']}; simulations={expected}, resumed={done}", flush=True)
    print(f"INI: {ini}\nResults: {out}", flush=True)
    logs = ini.parent / "logs"
    logs.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["V2X_INI"] = str(ini)
    began = time.perf_counter()
    newly_run = 0
    paired_offered: dict[tuple[float, int], tuple[float, float]] = {}
    for row in rows:
        key = (row["taskIntervalS"], row["seed"])
        offered = (row["offeredCritical"], row["offeredOrdinary"])
        if key in paired_offered and paired_offered[key] != offered:
            raise RuntimeError("Checkpoint contains unequal paired task streams")
        paired_offered[key] = offered
    for interval, period, policy, seed in cases:
        if (interval, period, policy, seed) in keys:
            continue
        config = f"{name}I{label_ms(interval)}" + (
            "FreshLeast" if policy == "FreshLeast" else f"P{label_ms(period)}{policy}")
        result = subprocess.run(["bash", str(HERE / "run.sh"), config, str(seed)],
                                cwd=HERE.parent.parent.parent, env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = logs / f"{config}-{seed}.log"
        log.write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f"Simulation failed; inspect {log}")
        raw = ini.parent / "results"
        scalar = raw / f"{config}-{seed}.sca"
        vector = raw / f"{config}-{seed}.vec"
        metrics = scalar_metrics(scalar)
        metrics.update(vector_metrics(vector))
        offered = metrics["offeredCritical"] + metrics["offeredOrdinary"]
        outcomes = (metrics["successCritical"] + metrics["successOrdinary"] +
                    metrics["lateCritical"] + metrics["lateOrdinary"] + metrics["unanswered"])
        if not math.isclose(offered, outcomes, abs_tol=.1):
            raise RuntimeError(f"Task outcome accounting failed for {config} seed {seed}: "
                               f"offered={offered}, outcomes={outcomes}")
        if offered <= 0 or metrics["stateReportsSent"] <= 0 or metrics["stateReportsReceived"] <= 0:
            raise RuntimeError(f"No tasks or packet-delivered reports in {config} seed {seed}")
        paired_key = (interval, seed)
        offered_pair = (metrics["offeredCritical"], metrics["offeredOrdinary"])
        if paired_key in paired_offered and paired_offered[paired_key] != offered_pair:
            raise RuntimeError(f"Unequal paired task streams: {config} seed {seed}")
        paired_offered[paired_key] = offered_pair
        row = {
            "taskIntervalS": interval, "reportPeriodS": period, "policy": policy,
            "seed": seed, "config": config, **metrics,
            "criticalCompletionRate": metrics["successCritical"] / metrics["offeredCritical"]
                if metrics["offeredCritical"] else 0.0,
            "ordinaryCompletionRate": metrics["successOrdinary"] / metrics["offeredOrdinary"]
                if metrics["offeredOrdinary"] else 0.0,
            "responseCoverage": metrics["responseCount"] / offered,
            "offeredLoadRatio": metrics["totalOfferedWorkUnits"] /
                (args.total_edge_rate * (args.duration - 10)),
            "meanResponseLatencyS": metrics["totalResponseLatency"] / metrics["responseCount"]
                if metrics["responseCount"] else None,
            "meanStateAgeAtDecisionS": None,
            "signalingPayloadBytesPerS": (metrics["stateBytesSent"] +
                                          metrics["stateSubscriptionBytesSent"]) / args.duration,
            "reportDeliveryFraction": metrics["stateReportsReceived"] / metrics["stateReportsSent"],
        }
        # The recorded scalar is a mean per UE; use the vector's raw mean for
        # the study-wide value rather than averaging vehicle means unequally.
        row["meanStateAgeAtDecisionS"] = report_age_mean(vector)
        rows.append(row)
        keys.add((interval, period, policy, seed))
        checkpoint(out, manifest, rows)
        if not args.retain_raw:
            for path in (scalar, vector, vector.with_suffix(".vci")):
                path.unlink(missing_ok=True)
        done += 1
        newly_run += 1
        elapsed = time.perf_counter() - began
        remaining = (expected - done) * elapsed / newly_run if newly_run else 0
        eta = time.strftime("%H:%M:%S", time.gmtime(remaining))
        print(f"[{done}/{expected} | {100*done/expected:.1f}% | ETA {eta}] "
              f"I={interval:g}s P={period:g}s {policy} seed={seed} "
              f"critical={row['criticalCompletionRate']:.3f} "
              f"reports={int(metrics['stateReportsReceived'])}", flush=True)
    summary = out.with_name(out.stem.replace("_results", "_summary") + ".csv")
    summarize(rows, summary)
    print(f"Complete. Per-run results: {out}\nSummary and plots: {summary.parent}", flush=True)


def report_age_mean(path: Path) -> float:
    names: set[str] = set()
    total = 0.0
    count = 0
    for line in path.open():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "vector" and parts[3] == "stateAgeAtDecision":
            names.add(parts[1])
        elif len(parts) >= 4 and parts[0] in names:
            total += float(parts[-1])
            count += 1
    return total / count if count else 0.0


if __name__ == "__main__":
    main()
