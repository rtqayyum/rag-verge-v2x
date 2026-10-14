"""Leakage-aware offline RAG evolution for the VERGE-V2X policy.

An LLM receives only retrieved *other-scenario* outcomes. Its verified profile
seeds a small bounded population. Candidates compete on explicitly selected
training seeds; the winner is then evaluated once on disjoint held-out seeds.
The LLM is never called on the packet scheduling path.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from rag_verge_smoke import (HERE, POLICY_BOUNDS, append_candidate_ini, call_llm,
                             load_memory, prompt_for, read_scalars, scenario_factors, verify)


def bounded(profile: dict[str, float]) -> dict[str, float]:
    return {key: max(low, min(high, float(profile[key])))
            for key, (low, high) in POLICY_BOUNDS.items()}


def population(llm_profile: dict[str, float]) -> list[dict[str, float]]:
    """A tiny auditable evolutionary neighbourhood around the LLM seed."""
    default = {"vergeReliabilityTarget": .90, "vergeDelayUncertainty": .08,
               "handoverRiskPenalty": .20, "failureRiskPenalty": 1.0,
               "replicationMaxAlternateQueue": .35, "ragOverloadQueueThreshold": .18}
    variants = [default, llm_profile]
    for target_delta, failure_delta, queue_delta in ((-.08, .50, -.12),
                                                       (-.04, .25, -.06),
                                                       (.04, -.20, .08),
                                                       (-.10, .75, .12)):
        p = dict(llm_profile)
        p["vergeReliabilityTarget"] += target_delta
        p["failureRiskPenalty"] += failure_delta
        p["replicationMaxAlternateQueue"] += queue_delta
        p["ragOverloadQueueThreshold"] += queue_delta
        variants.append(bounded(p))
    unique: list[dict[str, float]] = []
    for item in variants:
        if item not in unique:
            unique.append(item)
    return unique


def run(ini: Path, config: str, seed: int) -> dict[str, float]:
    env = os.environ.copy()
    env["V2X_INI"] = str(ini)
    process = subprocess.run(["bash", str(HERE / "run.sh"), config, str(seed)],
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    log = ini.parent / "logs" / f"{config}-{seed}.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text(process.stdout)
    if process.returncode:
        raise RuntimeError(f"{config} seed {seed} failed; inspect {log}")
    scalar = ini.parent / "results" / f"{config}-{seed}.sca"
    values = read_scalars(scalar)
    scalar.unlink(missing_ok=True)
    for extension in (".vec", ".vci"):
        scalar.with_suffix(extension).unlink(missing_ok=True)
    return values


def score(values: list[dict[str, float]]) -> float:
    """Selection objective declared before held-out evaluation."""
    completion = mean(item["criticalCompletionRate"] for item in values)
    latency = mean(item["meanResponseLatency"] for item in values)
    replicas = mean(item.get("replicatedTasks", 0.0) for item in values)
    return completion - .08 * min(latency, 10.0) - .00001 * replicas


def static_baselines(paths: list[Path], target: dict, test_seeds: list[int]) -> dict[str, list[dict]]:
    """Read paired static results without exposing target rows to RAG retrieval."""
    wanted = {"verge", "earliest", "risk", "replicate", "nearest"}
    values: dict[str, list[dict]] = {policy: [] for policy in wanted}
    for path in paths:
        payload = json.loads(path.read_text())
        for row in payload.get("rows", []):
            if (scenario_factors(row.get("config", "")) == target and row.get("seed") in test_seeds
                    and row.get("policy") in wanted):
                values[row["policy"]].append(row)
    for policy in wanted:
        values[policy].sort(key=lambda row: row["seed"])
        if [row["seed"] for row in values[policy]] != sorted(test_seeds):
            raise RuntimeError(f"Static {policy} rows for {target}, seeds {test_seeds} were not found")
    return values


def summary(values: list[dict[str, float]]) -> dict[str, float]:
    return {
        "criticalCompletionRate": mean(row["criticalCompletionRate"] for row in values),
        "meanResponseLatency": mean(row["meanResponseLatency"] for row in values),
        "replicatedTasks": mean(row.get("replicatedTasks", 0.0) for row in values),
        "ragOverloadFallbacks": mean(row.get("ragOverloadFallbacks", 0.0) for row in values),
        "selectionScore": score(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ini", type=Path, required=True)
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--memory-results", type=Path, nargs="+", required=True)
    parser.add_argument("--baseline-results", type=Path, nargs="+", required=True,
                        help="Completed static study JSON files used only for paired held-out comparison.")
    parser.add_argument("--train-seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--test-seeds", type=int, nargs="+", default=[3, 4])
    parser.add_argument("--provider", choices=("ollama", "openai-compatible"), default="ollama")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--candidate-limit", type=int, default=0,
                        help="Use the first N verified candidates; 0 evaluates the full population.")
    parser.add_argument("--name", default="RagVergeEvolve")
    args = parser.parse_args()
    if set(args.train_seeds) & set(args.test_seeds):
        parser.error("train and test seeds must be disjoint")
    source = args.ini.resolve()
    target = scenario_factors(args.base_config)
    memory = load_memory([path.resolve() for path in args.memory_results], target)
    baselines = static_baselines([path.resolve() for path in args.baseline_results], target,
                                 args.test_seeds)
    if len(memory) < args.top_k:
        parser.error(f"Only {len(memory)} non-leaking records available; require {args.top_k}")
    retrieved = memory[:args.top_k]
    proposal, metadata = call_llm(prompt_for(target, retrieved), args.provider, args.endpoint,
                                  args.model, args.api_key_env)
    seed_profile = verify(proposal)
    candidates = population(seed_profile)
    if args.candidate_limit:
        if args.candidate_limit < 1:
            parser.error("candidate-limit must be positive")
        candidates = candidates[:args.candidate_limit]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    trained = []
    for index, profile in enumerate(candidates):
        name = f"{args.name}{stamp}C{index}"
        candidate_ini = append_candidate_ini(source, name, args.base_config, profile)
        with candidate_ini.open("a") as stream:
            stream.write('*.ue[*].app[0].policy = "ragverge"\n')
        values = [run(candidate_ini, name, seed) for seed in args.train_seeds]
        trained.append({"candidate": name, "profile": profile, "training": values,
                        "trainingScore": score(values), "ini": str(candidate_ini)})
        print(f"candidate {index + 1}/{len(candidates)} score={trained[-1]['trainingScore']:.4f}", flush=True)
    winner = max(trained, key=lambda item: item["trainingScore"])
    held_out = [run(Path(winner["ini"]), winner["candidate"], seed) for seed in args.test_seeds]
    candidate_summary = summary(held_out)
    baseline_summary = {policy: summary(values) for policy, values in baselines.items()}
    paired_delta = {
        policy: {
            "criticalCompletionRate": candidate_summary["criticalCompletionRate"] - baseline["criticalCompletionRate"],
            "meanResponseLatency": candidate_summary["meanResponseLatency"] - baseline["meanResponseLatency"],
            "selectionScore": candidate_summary["selectionScore"] - baseline["selectionScore"],
        }
        for policy, baseline in baseline_summary.items()
    }
    output = source.parent / f"{args.name}{stamp}.result.json"
    output.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(), "target": target,
        "baseConfig": args.base_config, "retrievedMemory": retrieved, "llm": metadata,
        "llmSeedProfile": seed_profile, "selectionObjective": "completion - 0.08*mean_latency - 1e-5*replicas",
        "trainSeeds": args.train_seeds, "testSeeds": args.test_seeds,
        "candidates": trained, "winner": winner, "heldOut": held_out,
        "heldOutSummary": candidate_summary, "staticHeldOut": baselines,
        "staticHeldOutSummary": baseline_summary, "pairedDeltaVsStatic": paired_delta,
    }, indent=2) + "\n")
    print(f"winner={winner['candidate']} held-out-score={candidate_summary['selectionScore']:.4f}")
    print("paired held-out delta vs VERGE: "
          f"completion={paired_delta['verge']['criticalCompletionRate']:+.4f}, "
          f"latency={paired_delta['verge']['meanResponseLatency']:+.4f}s", flush=True)
    print(output)


if __name__ == "__main__":
    main()
