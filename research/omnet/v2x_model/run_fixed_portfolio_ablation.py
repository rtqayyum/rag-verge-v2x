"""Evaluate the fixed, no-LLM RAG-VERGE portfolio on held-out seeds.

This ablation retains the telemetry and overload switch but fixes every policy
parameter before seeing any retrieval record or LLM proposal.  It therefore
isolates the incremental value of the RAG-LLM evolution used in a completed
RAG portfolio manifest.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rag_verge_evolve import run, score, summary
from rag_verge_smoke import append_candidate_ini


FIXED_PROFILE = {
    "vergeReliabilityTarget": 0.90,
    "vergeDelayUncertainty": 0.08,
    "handoverRiskPenalty": 0.20,
    "failureRiskPenalty": 1.00,
    "replicationMaxAlternateQueue": 0.35,
    "ragOverloadQueueThreshold": 0.18,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--tag", default="FixedPortfolioAblationV1")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    study = json.loads(args.manifest.read_text())
    output = args.manifest.parent / f"{args.tag}_results.json"
    completed: list[dict] = []
    if args.resume and output.exists():
        completed = json.loads(output.read_text()).get("rows", [])
    completed_keys = {(x["vehicles"], x["rsus"], x["condition"]) for x in completed}

    for index, item in enumerate(study["completed"], 1):
        key = (item["vehicles"], item["rsus"], item["condition"])
        if key in completed_keys:
            print(f"[{index}/{len(study['completed'])}] already complete {key}", flush=True)
            continue
        result_path = Path(item["result"])
        if not result_path.is_absolute():
            result_path = HERE / result_path
        evolved = json.loads(result_path.read_text())
        base_ini = Path(evolved["winner"]["ini"])
        if not base_ini.is_absolute():
            base_ini = HERE / base_ini
        name = f"{args.tag}V{item['vehicles']}R{item['rsus']}{item['condition'].title()}"
        ini = append_candidate_ini(base_ini, name, evolved["baseConfig"], FIXED_PROFILE)
        with ini.open("a") as stream:
            stream.write('*.ue[*].app[0].policy = "ragverge"\n')
        print(f"[{index}/{len(study['completed'])}] fixed portfolio V{item['vehicles']} R{item['rsus']} {item['condition']}", flush=True)
        held_out = [run(ini, name, seed) for seed in evolved["testSeeds"]]
        fixed = summary(held_out)
        rag = evolved["heldOutSummary"]
        completed.append({
            **item, "ini": str(ini), "testSeeds": evolved["testSeeds"], "profile": FIXED_PROFILE,
            "heldOut": held_out, "heldOutSummary": fixed,
            "deltaRagMinusFixed": {
                "criticalCompletionRate": rag["criticalCompletionRate"] - fixed["criticalCompletionRate"],
                "meanResponseLatency": rag["meanResponseLatency"] - fixed["meanResponseLatency"],
                "selectionScore": rag["selectionScore"] - fixed["selectionScore"],
            },
        })
        output.write_text(json.dumps({
            "created_utc": datetime.now(timezone.utc).isoformat(), "sourceManifest": str(args.manifest),
            "fixedProfile": FIXED_PROFILE, "rows": completed,
        }, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
