"""Run the integrated packet-report policy-search campaign.

The campaign has two immutable stages.  Stage A builds a policy--outcome
memory from varied bounded profiles on training seeds.  Stage B freezes the
retrieved-LLM, no-retrieval-LLM, random-search, and kernel-surrogate choices
and evaluates those choices with the same packet model on held-out seeds.
No exact busy-until state is used by deployable policies.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from generate_dubai import generate
from integrated_common import (BASELINES, HERE, PolicyProfile,
                               prepare_integrated_ini, run_case, source_hash)


POOL = [
    PolicyProfile(2, 0.0, 0.0, 1.0),
    PolicyProfile(2, 0.5, 0.15, 1.5),
    PolicyProfile(2, 1.0, 0.35, 2.0),
    PolicyProfile(2, 1.5, 0.60, 2.5),
    PolicyProfile(3, 0.5, 0.15, 1.5),
    PolicyProfile(3, 1.0, 0.35, 2.0),
    PolicyProfile(4, 0.5, 0.15, 1.5),
    PolicyProfile(4, 1.5, 0.60, 2.5),
]


def profile_from_json(value: dict) -> PolicyProfile:
    required = ("candidateSampleSize", "agePenalty", "freshnessPenalty",
                "freshnessCriticalBoost")
    if not all(key in value for key in required):
        for nested in value.values():
            if isinstance(nested, dict) and all(key in nested for key in required):
                value = nested
                break
    aliases = {
        "candidate_sample_size": "candidateSampleSize",
        "candidateCount": "candidateSampleSize",
        "age_penalty": "agePenalty",
        "freshness_penalty": "freshnessPenalty",
        "freshness_critical_boost": "freshnessCriticalBoost",
        "critical_boost": "freshnessCriticalBoost",
    }
    value = {aliases.get(key, key): item for key, item in value.items()}
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError(f"LLM proposal is missing bounded fields: {missing}; received={value}")
    return PolicyProfile(int(value["candidateSampleSize"]),
                         float(value["agePenalty"]),
                         float(value["freshnessPenalty"]),
                         float(value["freshnessCriticalBoost"]))


def llm_profile(memory: list[dict], provider: str, endpoint: str,
                model: str, with_retrieval: bool) -> tuple[PolicyProfile, dict]:
    records = memory[:8] if with_retrieval else []
    prompt = {
        "task": "Design one bounded packet-report server-selection profile.",
        "constraints": {
            "candidateSampleSize": "integer 2..4",
            "agePenalty": "number 0..2",
            "freshnessPenalty": "number 0..1",
            "freshnessCriticalBoost": "number 1..3",
        },
        "objective": "maximize critical deadline completion while preserving ordinary completion",
        "evidence": records,
        "return": "JSON only with exactly the four constraint keys",
    }
    if provider != "ollama":
        raise RuntimeError("Only the local Ollama provider is supported for this offline campaign")
    body = json.dumps({"model": model, "prompt": json.dumps(prompt), "stream": False,
                       "format": "json"}).encode()
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read())
    text = payload.get("response", "")
    proposal = json.loads(text)
    profile = profile_from_json(proposal).checked(4)
    return profile, {"provider": provider, "model": model, "retrieval": with_retrieval,
                     "raw": proposal, "prompt": prompt,
                     "responseDurationNanos": payload.get("total_duration")}


def aggregate(rows: list[dict], profile_key: str | None = None) -> dict:
    selected = [r for r in rows if profile_key is None or r.get("profileKey") == profile_key]
    if not selected:
        raise RuntimeError("No rows for requested profile")
    return {"n": len(selected),
            "criticalCompletion": mean(r["criticalCompletionRate"] for r in selected),
            "ordinaryCompletion": mean(r["ordinaryCompletionRate"] for r in selected),
            "coverage": mean(r["responseCoverage"] for r in selected),
            "latency": mean(r["meanResponseLatencyS"] or 0.0 for r in selected),
            "rejectedCritical": mean(r["criticalRejectionRate"] for r in selected)}


def surrogate_select(rows: list[dict], profiles: list[PolicyProfile],
                     ordinary_floor: float) -> PolicyProfile:
    """Choose a profile with a small Gaussian kernel surrogate.

    The predictor uses only development outcomes and profile coordinates.  It
    is deliberately simple and deterministic so it is a reproducible search
    control, rather than an additional claimed contribution.
    """
    scored = []
    scales = (1.0, 1.0, 1.0, 1.0)
    for profile in profiles:
        estimates = []
        for candidate in profiles:
            key = candidate.key
            observed = [r for r in rows if r.get("profileKey") == key]
            if not observed:
                continue
            distance = sum(((a - b) / scale) ** 2 for a, b, scale in zip(
                profile.as_tuple(), candidate.as_tuple(), scales))
            weight = math.exp(-distance / 2.0)
            estimates.append((weight, observed))
        total = sum(weight for weight, _ in estimates) or 1.0
        critical = sum(weight * mean(r["criticalCompletionRate"] for r in obs)
                       for weight, obs in estimates) / total
        ordinary = sum(weight * mean(r["ordinaryCompletionRate"] for r in obs)
                       for weight, obs in estimates) / total
        if ordinary >= ordinary_floor:
            scored.append((critical, profile))
    return max(scored, key=lambda item: item[0])[1] if scored else profiles[0]


def target_interval(metadata: dict, load: float, capacity: float) -> float:
    return round(1000 * metadata["mean_active_vehicles"] * 1.5 /
                 (capacity * load)) / 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "heldout", "all"), default="all")
    parser.add_argument("--study-tag", default="IntegratedCampaignV1")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--rsus", type=int, default=4)
    parser.add_argument("--total-edge-rate", type=float, default=160.0)
    parser.add_argument("--loads", type=float, nargs="+", default=[0.8, 1.1])
    parser.add_argument("--reports", type=float, nargs="+", default=[0.5, 1.0])
    parser.add_argument("--train-seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--test-seeds", type=int, nargs="+", default=[3, 4])
    parser.add_argument("--provider", choices=("ollama",), default="ollama")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    scenario = args.scenario.resolve()
    metadata = json.loads((scenario / "metadata.json").read_text())
    if set(args.train_seeds) & set(args.test_seeds):
        parser.error("training and held-out seeds must be disjoint")
    development = GENERATED = HERE / "scenario" / "generated"
    dev_name = f"{args.study_tag}DevelopmentV{metadata['vehicles_exported']}R{args.rsus}"
    intervals = [target_interval(metadata, load, args.total_edge_rate) for load in args.loads]
    profiles = [p.checked(args.rsus) for p in POOL]
    dev_ini = prepare_integrated_ini(scenario, args.rsus, args.total_edge_rate, dev_name,
                                     intervals, args.reports, profiles)
    dev_out = GENERATED / f"{dev_name}_results.json"
    dev_rows: list[dict] = []
    if dev_out.exists():
        if not args.resume:
            raise RuntimeError(f"Development output exists; use --resume: {dev_out}")
        dev_rows = json.loads(dev_out.read_text())["rows"]
    done = {(r["config"], r["seed"]) for r in dev_rows}
    cases = []
    for interval in intervals:
        for report in args.reports:
            ilabel, plabel = round(interval * 1000), round(report * 1000)
            for method in BASELINES:
                cases.extend((f"{dev_name}I{ilabel}P{plabel}Control{method}", seed,
                              method, None, interval, report) for seed in args.train_seeds)
            for profile in profiles:
                cases.extend((f"{dev_name}I{ilabel}P{plabel}Rag{profile.key}", seed,
                              "RAG-VERGE-profile", profile, interval, report)
                             for seed in args.train_seeds)
    if args.stage in ("development", "all"):
        for index, (config, seed, method, profile, interval, report) in enumerate(cases, 1):
            if (config, seed) in done:
                continue
            row = run_case(dev_ini, config, seed, 60.0, args.total_edge_rate)
            row.update(method=method, profileKey=profile.key if profile else None,
                       profile=profile.__dict__ if profile else None,
                       taskIntervalS=interval, reportPeriodS=report)
            dev_rows.append(row)
            dev_out.write_text(json.dumps({"manifest": {"stage": "development",
                "sourceSha256": source_hash(), "rngSeparation": {"task": 0, "selection": 1},
                "deadlineAdmission": True, "loads": args.loads, "reports": args.reports},
                "rows": dev_rows}, indent=2) + "\n")
            print(f"[development {index}/{len(cases)}] {method} seed={seed} "
                  f"critical={row['criticalCompletionRate']:.3f}", flush=True)
    if args.stage == "development":
        print(dev_out)
        return
    if not dev_rows:
        raise RuntimeError("Development rows are required before held-out selection")
    # Build a leakage-safe memory containing policy/outcome pairs, then retrieve
    # the nearest records for the LLM proposal.
    memory = []
    for row in dev_rows:
        if row["profileKey"]:
            memory.append({"profile": row["profile"], "profileKey": row["profileKey"],
                           "taskIntervalS": row["taskIntervalS"], "reportPeriodS": row["reportPeriodS"],
                           "criticalCompletion": row["criticalCompletionRate"],
                           "ordinaryCompletion": row["ordinaryCompletionRate"],
                           "rejectedCritical": row["criticalRejectionRate"],
                           "coverage": row["responseCoverage"]})
    memory.sort(key=lambda r: (-r["criticalCompletion"], r["rejectedCritical"]))
    rag, rag_meta = llm_profile(memory, args.provider, args.endpoint, args.model, True)
    no_rag, no_rag_meta = llm_profile(memory, args.provider, args.endpoint, args.model, False)
    power2_rows = [r for r in dev_rows if r["method"] == "Power2"]
    baseline_ordinary = aggregate(power2_rows)["ordinaryCompletion"]
    profile_scores = []
    for p in profiles:
        summary = aggregate(dev_rows, p.key)
        feasible = summary["ordinaryCompletion"] >= baseline_ordinary - 0.02
        profile_scores.append((summary["criticalCompletion"] if feasible else -1.0, p, summary))
    random.seed(20261019)
    random_choice = random.choice(profiles)
    surrogate_choice = surrogate_select(dev_rows, profiles,
                                        baseline_ordinary - 0.02)
    selected = {"RAG-retrieval": rag, "LLM-no-retrieval": no_rag,
                "Random-search": random_choice, "Kernel-surrogate": surrogate_choice}
    selected_profiles = list({p.key: p for p in selected.values()}.values())
    hold_name = f"{args.study_tag}HeldoutV{metadata['vehicles_exported']}R{args.rsus}"
    hold_ini = prepare_integrated_ini(scenario, args.rsus, args.total_edge_rate, hold_name,
                                      intervals, args.reports, selected_profiles)
    hold_out = GENERATED / f"{hold_name}_results.json"
    hold_rows = []
    if hold_out.exists():
        if not args.resume:
            raise RuntimeError(f"Held-out output exists; use --resume: {hold_out}")
        hold_rows = json.loads(hold_out.read_text())["rows"]
    hold_cases = []
    for interval in intervals:
        for report in args.reports:
            ilabel, plabel = round(interval * 1000), round(report * 1000)
            for method, profile in BASELINES.items():
                hold_cases.extend((f"{hold_name}I{ilabel}P{plabel}Control{method}", seed,
                                   method, None, interval, report) for seed in args.test_seeds)
            for label, profile in selected.items():
                hold_cases.extend((f"{hold_name}I{ilabel}P{plabel}Rag{profile.key}", seed,
                                   label, profile, interval, report) for seed in args.test_seeds)
    done = {(r["config"], r["seed"]) for r in hold_rows}
    for index, (config, seed, method, profile, interval, report) in enumerate(hold_cases, 1):
        if (config, seed) in done:
            continue
        row = run_case(hold_ini, config, seed, 60.0, args.total_edge_rate)
        row.update(method=method, profileKey=profile.key if profile else None,
                   profile=profile.__dict__ if profile else None,
                   taskIntervalS=interval, reportPeriodS=report)
        hold_rows.append(row)
        hold_out.write_text(json.dumps({"manifest": {"stage": "heldout",
            "sourceSha256": source_hash(),
            "selection": {key: value.__dict__ for key, value in selected.items()},
            "llmRetrieval": rag_meta, "llmNoRetrieval": no_rag_meta,
            "selectionObjective": "maximize critical completion subject to ordinary completion >= Power2 - 0.02",
            "trainSeeds": args.train_seeds, "testSeeds": args.test_seeds},
            "rows": hold_rows}, indent=2) + "\n")
        print(f"[heldout {index}/{len(hold_cases)}] {method} seed={seed} "
              f"critical={row['criticalCompletionRate']:.3f}", flush=True)
    print(json.dumps({"development": str(dev_out), "heldout": str(hold_out),
                      "selected": {k: v.__dict__ for k, v in selected.items()},
                      "memoryRecords": len(memory)}, indent=2))


if __name__ == "__main__":
    main()
