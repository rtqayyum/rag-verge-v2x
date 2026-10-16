"""Audit and summarize completed packet-state studies without pooling designs.

Usage: python analyze_packet_telemetry.py
Inputs are explicitly enumerated so smoke runs cannot enter publication tables.
Exact paired sign-flip tests are exploratory; Holm correction covers the twelve
FreshPower2/Power2 critical-completion comparisons. Seeds, not tasks, are units.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

HERE = Path(__file__).resolve().parent
OUT = HERE / "analysis" / "packet_telemetry_v1"
FILES = [
    "StaleGateV2DowntownV75R4_stale_screen_results.json",
    "FreshP2ValidationDowntownV75R4_stale_screen_results.json",
    "FinalFreshP2V25R4DowntownV25R4_stale_screen_results.json",
    "FinalFreshP2V150R8DowntownV150R8_stale_screen_results.json",
]
MAIN = ["StaleLeast", "AgeAware", "Power2", "FreshPower2"]
COLORS = dict(zip(MAIN, ["#3366aa", "#008877", "#d18400", "#8833aa"]))
METRICS = ["criticalCompletionRate", "ordinaryCompletionRate", "responseCoverage",
           "meanResponseLatencyS", "p95ResponseLatency", "p99ResponseLatency",
           "meanStateAgeAtDecisionS", "signalingPayloadBytesPerS",
           "reportDeliveryFraction", "offeredLoadRatio", "meanQueueDelayAllArrivalsS"]


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def exact_paired_p(differences):
    observed = abs(mean(differences))
    permutations = [abs(mean(s * d for s, d in zip(signs, differences)))
                    for signs in itertools.product((-1, 1), repeat=len(differences))]
    return sum(v >= observed - 1e-12 for v in permutations) / len(permutations)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, provenance = [], []
    for name in FILES:
        path = HERE / "scenario" / "generated" / name
        data = json.loads(path.read_text())
        m = data["manifest"]
        seen, streams = set(), {}
        for r in data["rows"]:
            key = (r["taskIntervalS"], r["reportPeriodS"], r["policy"], r["seed"])
            if key in seen:
                raise ValueError(f"Duplicate observation in {name}: {key}")
            seen.add(key)
            offered = r["offeredCritical"] + r["offeredOrdinary"]
            outcomes = sum(r[k] for k in ("successCritical", "successOrdinary",
                                          "lateCritical", "lateOrdinary", "unanswered"))
            if not math.isclose(offered, outcomes, abs_tol=.1):
                raise ValueError(f"Task accounting failed: {name} {key}")
            stream_key = (r["taskIntervalS"], r["seed"])
            signature = (r["offeredCritical"], r["offeredOrdinary"], r["totalOfferedWorkUnits"])
            if stream_key in streams and signature != streams[stream_key]:
                raise ValueError(f"Offered streams differ: {name} {key}")
            streams[stream_key] = signature
            if r["stateReportsReceived"] <= 0 or r["stateReportsSent"] <= 0:
                raise ValueError("No delivered telemetry")
            if not math.isclose(r["criticalCompletionRate"],
                                r["successCritical"] / r["offeredCritical"], abs_tol=1e-12):
                raise ValueError("Critical rate does not match counts")
            rows.append({"study": m["studyTag"], "vehicles": m["vehicles"],
                         "rsus": m["rsus"], "mobilitySeed": m["mobilitySeed"],
                         "meanActiveVehicles": m["meanActiveVehicles"],
                         "peakActiveVehicles": m["peakActiveVehicles"], **r,
                         "meanQueueDelayAllArrivalsS": r["totalQueueDelay"] /
                         max(1, r["tasksReceived"] - r["tasksDroppedFailure"])})
        policies = sorted({r["policy"] for r in data["rows"] if r["policy"] != "FreshLeast"})
        expected = (len(m["taskIntervalsS"]) * len(m["reportPeriodsS"]) * len(policies)
                    + len(m["taskIntervalsS"])) * m["networkSeeds"]
        if len(seen) != expected:
            raise ValueError(f"Incomplete design {name}: {len(seen)}/{expected}")
        expected_keys = {(i, p, policy, seed) for i in m["taskIntervalsS"]
                         for p in m["reportPeriodsS"] for policy in policies
                         for seed in range(m["networkSeeds"])}
        reference_period = m["reportPeriodsS"][len(m["reportPeriodsS"])//2]
        expected_keys.update((i, reference_period, "FreshLeast", seed)
                             for i in m["taskIntervalsS"] for seed in range(m["networkSeeds"]))
        if seen != expected_keys:
            raise ValueError(f"Design keys do not match manifest: {name}")
        ini = path.with_name(data["rows"][0]["config"].split("I")[0] + ".ini")
        if not ini.exists() or hashlib.sha256(ini.read_bytes()).hexdigest() != m["iniSha256"]:
            raise ValueError(f"INI missing or changed for {name}")
        mobility_id = "StaleGateV2" if m["vehicles"] == 75 else "StaleScaleV2"
        scenario = HERE / "scenario" / "dubai" / (
            f"downtown-v{m['vehicles']}-s1-{mobility_id}-d60-dt0p5")
        for filename, hashkey in [("sumo.movements", "traceSha256"),
                                  ("routes.rou.xml", "routesSha256")]:
            if hashlib.sha256((scenario / filename).read_bytes()).hexdigest() != m[hashkey]:
                raise ValueError(f"Archived mobility hash mismatch: {scenario / filename}")
        provenance.append({"input": str(path.relative_to(HERE)),
                           "fileSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "rows": len(seen), "policies": policies, "manifest": m})
    groups = defaultdict(list)
    for r in rows:
        groups[(r["study"], r["vehicles"], r["rsus"], r["taskIntervalS"],
                r["reportPeriodS"], r["policy"])].append(r)
    summary = []
    for (study, vehicles, rsus, interval, period, policy), members in sorted(groups.items()):
        item = dict(study=study, vehicles=vehicles, rsus=rsus, taskIntervalS=interval,
                    reportPeriodS=period, policy=policy, n=len(members))
        for metric in METRICS:
            values = [r[metric] for r in members if r.get(metric) is not None]
            item[metric + "Mean"] = mean(values) if values else None
            item[metric + "SD"] = stdev(values) if len(values) > 1 else None
        summary.append(item)
    pairs = []
    for key, members in sorted(groups.items()):
        if key[-1] != "FreshPower2":
            continue
        controls = {r["seed"]: r for r in groups[key[:-1] + ("Power2",)]}
        if set(controls) != {r["seed"] for r in members}:
            raise ValueError("Unpaired seeds")
        differences = [r["criticalCompletionRate"] - controls[r["seed"]]["criticalCompletionRate"]
                       for r in sorted(members, key=lambda x: x["seed"])]
        pairs.append(dict(study=key[0], vehicles=key[1], rsus=key[2], taskIntervalS=key[3],
                          reportPeriodS=key[4], n=len(members),
                          meanDifferencePP=100*mean(differences),
                          sdDifferencePP=100*stdev(differences),
                          minDifferencePP=100*min(differences), maxDifferencePP=100*max(differences),
                          wins=sum(d > 0 for d in differences),
                          exactTwoSidedP=exact_paired_p(differences), holmP=None,
                          ordinaryDifferencePP=100*mean(r["ordinaryCompletionRate"] -
                              controls[r["seed"]]["ordinaryCompletionRate"] for r in members),
                          signalingDifferencePct=100*(mean(r["signalingPayloadBytesPerS"] for r in members)/
                              mean(r["signalingPayloadBytesPerS"] for r in controls.values())-1)))
    maximum = 0
    for rank, p in enumerate(sorted(pairs, key=lambda x: x["exactTwoSidedP"])):
        maximum = max(maximum, min(1, (len(pairs)-rank)*p["exactTwoSidedP"]))
        p["holmP"] = maximum
    write_csv(OUT / "per_run.csv", rows)
    write_csv(OUT / "summary.csv", summary)
    write_csv(OUT / "paired_comparisons.csv", pairs)
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2)+"\n")
    plots(summary, pairs)
    improved = sum(p["meanDifferencePP"] > 0 for p in pairs)
    report = f"""# Packet telemetry analysis, 16 October 2026

Audited {len(rows)} run records across four archived studies. All task counts,
offered workload signatures within paired cells, expected run totals, and
archived INI hashes reconcile. Smoke runs are excluded. The original screen
has 80 runs; method validation has 72; the two scaling batches have 78 each.

FreshPower2 has a positive mean difference over Power2 in {improved}/{len(pairs)}
cells. No critical-completion comparison has a Holm-adjusted two-sided exact
paired sign-flip p-value below 0.05. With only 3 or 4 seeds per cell, the
smallest possible two-sided p-values are 0.25 and 0.125. These are descriptive
pilot results, not independent confirmatory evidence: method design followed
the original screen, and the same mobility and seed sets were reused.

## Interpretation and audit qualifications

- 25/4, 75/4, and 150/8 are joint vehicle/server configurations. The 150/8
  point does not isolate vehicle scaling or RSU scaling. The promised full
  4-density by 5-RSU matrix has NOT been completed.
- Reporting period and payload size are controlled; realized transmitted
  payload bytes differ across policies because subscription delivery and
  vehicle activity interact with the packet network. This is a matched
  reporting configuration, not an exact matched-byte budget. The scatter
  plot reports measured cost. Full radio-frame overhead is not recorded.
- FreshPower2 score = 2*baseNetworkDelay + max(0,busyUntil-now) + work/rate
  + (agePenalty + freshnessPenalty*boost)*arrivalProxy*age.
  boost=2 for critical tasks and 1 otherwise; agePenalty=1 and
  freshnessPenalty=0.35. Missing-report queue cost is 1 second.
- `FreshP2NoFreshness` sets ONLY freshnessPenalty=0, retaining agePenalty=1.
  Its plot label is "No extra penalty". `FreshP2NoCritical` sets boost=1.
  Power2 removes all age correction and uses a different missing-report cost.
  Consequently a difference from Power2 cannot isolate the extra penalty.
- The arrivalProxy is an EWMA of positive busy-until increments over report
  spacing, not an unbiased measurement of work arrival rate.
- Queues are FIFO. Criticality changes selection scores; it does not reorder
  the server queue. There is no decision-triggered reporting, expiry admission,
  or new LLM/RAG component in these runs.
- Dynamic handover remains disabled. Reported task latency includes a modeled
  50-ms boundary-crossing charge. Initial UE attachment follows departure position.
- Latency quantiles are conditional on returned tasks. Mean queue delay uses
  all admitted arrivals; it can include work finishing after the horizon.
- One trip seed per vehicle count, 60-second traces, 160 work units/s total.
  Load ratio is an offered-work proxy divided by 50 seconds of total capacity;
  vehicle activity is nonstationary. Exported cars are not simultaneous cars.
- Historical source hashes are preserved. Current source differs across
  study stages, and exact historical source snapshots were not saved for
  every stage. The current checkout must use a new tag when rerunning.

## Figure guide

01: critical completion across report periods, with between-seed SD.
02: twelve paired Power2 differences; each dot is one seed, diamonds are means.
03: ordinary completion and response coverage, alongside critical completion.
04: returned-task p95 latency and all-admitted-arrival queue delay.
05: measured signaling/completion and report-age/completion scatter plots.
06: ablations for 25/4 and 150/8; bars are means, whiskers are SD.
07: original 75/4 screen over 0.1, 0.5, 1.0-second reporting periods.

All plots are exported as PNG and SVG. Summary CSV and paired comparison CSV
preserve study membership. No pooled tasks-as-replicates significance test is used.
"""
    (OUT / "REPORT.md").write_text(report)
    print(report)
    print("Paired differences (percentage points):")
    for p in pairs:
        print(p["vehicles"], p["rsus"], p["taskIntervalS"], p["reportPeriodS"],
              round(p["meanDifferencePP"], 3), p["exactTwoSidedP"], p["holmP"])


def plots(summary, pairs):
    os.environ.setdefault("MPLCONFIGDIR", str(OUT / ".matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    configurations = [(25, 4), (75, 4), (150, 8)]
    def select(v, m, interval, policy):
        return sorted([r for r in summary if r["vehicles"] == v and r["rsus"] == m and
                       r["taskIntervalS"] == interval and r["policy"] == policy and
                       r["study"] != "StaleGateV2"], key=lambda r: r["reportPeriodS"])
    def save(fig, stem, legend=True):
        if legend:
            handles, labels = fig.axes[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False)
        fig.tight_layout(rect=(0, 0, 1, .94 if legend else 1))
        for suffix in ("png", "svg"):
            fig.savefig(OUT / f"{stem}.{suffix}", dpi=220)
        plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(10, 5.4), sharey=True, sharex=True)
    for col, (v, m) in enumerate(configurations):
        for row, interval in enumerate((.6, .3)):
            ax = axes[row, col]
            for policy in MAIN:
                points = select(v, m, interval, policy)
                ax.errorbar([p["reportPeriodS"] for p in points],
                            [p["criticalCompletionRateMean"] for p in points],
                            yerr=[p["criticalCompletionRateSD"] for p in points],
                            marker="o", capsize=3, color=COLORS[policy], label=policy)
            ax.set(title=f"{v} exported cars / {m} RSUs; tasks {interval:g} s",
                   xticks=[.5, 1], ylim=(0, 1.02), xlabel="Report period (s)")
            ax.grid(alpha=.2)
    axes[0, 0].set_ylabel("Critical completion")
    axes[1, 0].set_ylabel("Critical completion")
    save(fig, "01_critical_completion")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, p in enumerate(pairs):
        # Read the paired run records, rather than manufacture distributional samples.
        runrows = list(csv.DictReader((OUT / "per_run.csv").open()))
        subset = [r for r in runrows if r["study"] == p["study"] and
                  float(r["taskIntervalS"]) == p["taskIntervalS"] and
                  float(r["reportPeriodS"]) == p["reportPeriodS"]]
        baselines = {r["seed"]: float(r["criticalCompletionRate"]) for r in subset
                     if r["policy"] == "Power2"}
        delta = [100*(float(r["criticalCompletionRate"])-baselines[r["seed"]])
                 for r in subset if r["policy"] == "FreshPower2"]
        ax.scatter(delta, [i]*len(delta), color="#999999", s=20)
        ax.scatter([p["meanDifferencePP"]], [i], marker="D", color="#8833aa", s=32)
    ax.axvline(0, color="black", lw=.8)
    ax.set(yticks=range(len(pairs)), yticklabels=[
        f"{p['vehicles']}/{p['rsus']}: tasks {p['taskIntervalS']:g}s, reports {p['reportPeriodS']:g}s"
        for p in pairs], xlabel="FreshPower2 minus Power2 critical completion (percentage points)")
    ax.grid(axis="x", alpha=.2)
    save(fig, "02_paired_effects", False)
    for stem, metrics in [
        ("03_completion_and_coverage", [("criticalCompletionRate", "Critical completion"),
            ("ordinaryCompletionRate", "Ordinary completion"), ("responseCoverage", "Response coverage")]),
        ("04_latency_and_queue", [("p95ResponseLatency", "Returned-task p95 latency (s)"),
            ("meanQueueDelayAllArrivalsS", "Mean queue wait, all admitted arrivals (s)")])]:
        fig, axes = plt.subplots(len(metrics), 3, figsize=(10, 2.2*len(metrics)), squeeze=False)
        for row, (metric, label) in enumerate(metrics):
            for col, (v, m) in enumerate(configurations):
                ax = axes[row, col]
                for policy in MAIN:
                    points = select(v, m, .3, policy)
                    ax.plot([p["reportPeriodS"] for p in points], [p[metric+"Mean"] for p in points],
                            marker="o", color=COLORS[policy], label=policy)
                ax.set(title=f"{v} cars / {m} RSUs; tasks 0.3 s", xlabel="Report period (s)", xticks=[.5, 1])
                if col == 0: ax.set_ylabel(label)
                if "completion" in stem: ax.set_ylim(0, 1.02)
                ax.grid(alpha=.2)
        save(fig, stem)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, (metric, label) in zip(axes, [("signalingPayloadBytesPerS", "State signaling payload (kB/s)"),
                                         ("meanStateAgeAtDecisionS", "Mean report age at selection (s)")]):
        for policy in MAIN:
            for v, m in configurations:
                points = select(v, m, .6, policy)
                ax.scatter([p[metric+"Mean"]/(1000 if "Bytes" in metric else 1) for p in points],
                           [p["criticalCompletionRateMean"] for p in points], color=COLORS[policy],
                           marker={25:"o", 75:"s", 150:"^"}[v], label=policy if v==25 else None)
                for p in points:
                    ax.annotate(f"{v}/{m}", (p[metric+"Mean"]/(1000 if "Bytes" in metric else 1),
                                p["criticalCompletionRateMean"]), xytext=(3, 3), textcoords="offset points", fontsize=6)
        ax.set(xlabel=label, ylabel="Critical completion; task interval 0.6 s", ylim=(0, 1.02))
        ax.grid(alpha=.2)
    save(fig, "05_cost_and_age")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    ablations = ["Power2", "FreshP2NoFreshness", "FreshP2NoCritical", "FreshPower2"]
    labels = ["Power2", "No extra penalty", "No critical boost", "FreshPower2"]
    for ax, (v, m) in zip(axes, [(25, 4), (150, 8)]):
        cells = [(i, p) for i in (.6, .3) for p in (.5, 1)]
        x = np.arange(4)
        for k, (policy, label) in enumerate(zip(ablations, labels)):
            points = [next(r for r in select(v, m, i, policy) if r["reportPeriodS"] == p) for i, p in cells]
            ax.bar(x+(k-1.5)*.19, [p["criticalCompletionRateMean"] for p in points], width=.19,
                   yerr=[p["criticalCompletionRateSD"] for p in points], capsize=2, label=label,
                   color={"Power2":"#d18400", "FreshP2NoFreshness":"#4477aa",
                          "FreshP2NoCritical":"#008877", "FreshPower2":"#8833aa"}[policy])
        ax.set(title=f"{v} cars / {m} RSUs", xticks=x, xticklabels=[f"{i:g}/{p:g}" for i,p in cells],
               xlabel="Task interval / report period (s)", ylim=(0, 1.05))
    axes[0].set_ylabel("Critical completion")
    save(fig, "06_ablation")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, interval in zip(axes, (.6, .3)):
        for policy in MAIN[:3]:
            points = sorted([r for r in summary if r["study"] == "StaleGateV2" and
                             r["taskIntervalS"] == interval and r["policy"] == policy],
                            key=lambda r: r["reportPeriodS"])
            ax.errorbar([p["reportPeriodS"] for p in points], [p["criticalCompletionRateMean"] for p in points],
                        yerr=[p["criticalCompletionRateSD"] for p in points], marker="o", capsize=3,
                        color=COLORS[policy], label=policy)
        ax.set(title=f"75 cars / 4 RSUs; tasks {interval:g} s", xlabel="Report period (s)", ylim=(0, 1.02))
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Critical completion")
    save(fig, "07_original_screen")




if __name__ == "__main__":
    main()
