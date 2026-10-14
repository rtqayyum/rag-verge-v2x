"""Leakage-free external-map validation for RAG-VERGE.

Static baselines are generated on an unseen map.  Retrieved RAG memory comes
only from a different completed map, while seeds 0--2 select the bounded
candidate and seeds 3--9 are held out for paired evaluation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
GENERATED = HERE / "scenario" / "generated"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-results", type=Path, nargs="+", required=True)
    parser.add_argument("--memory-results", type=Path, nargs="+", required=True)
    parser.add_argument("--source-tag", required=True,
                        help="Static study tag, for example ExternalMarinaV1.")
    parser.add_argument("--area", choices=["marina", "szr"], required=True)
    parser.add_argument("--study-tag", default="CrossMapRagV1")
    parser.add_argument("--vehicles", type=int, nargs="+", default=[75, 150])
    parser.add_argument("--rsus", type=int, nargs="+", default=[6, 10], choices=[2, 4, 6, 8, 10])
    parser.add_argument("--conditions", nargs="+", default=["burst", "failure"],
                        choices=["nominal", "burst", "failure"])
    parser.add_argument("--train-seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--test-seeds", type=int, nargs="+", default=[3, 4, 5, 6, 7, 8, 9])
    parser.add_argument("--provider", choices=["ollama", "openai-compatible"], default="ollama")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if set(args.train_seeds) & set(args.test_seeds):
        parser.error("train and test seeds must be disjoint")
    baselines, memory = [p.resolve() for p in args.baseline_results], [p.resolve() for p in args.memory_results]
    if not all(p.exists() for p in baselines + memory):
        parser.error("Every supplied result JSON must exist")
    suffix = {"nominal": "", "burst": "Burst", "failure": "Failure"}
    targets = [(v, r, c) for v in args.vehicles for r in args.rsus for c in args.conditions]
    manifest = GENERATED / f"{args.study_tag}_manifest.json"
    completed = json.loads(manifest.read_text()).get("completed", []) if args.resume and manifest.exists() else []
    done = {(x["vehicles"], x["rsus"], x["condition"]) for x in completed}
    for index, (vehicles, rsus, condition) in enumerate(targets, 1):
        if (vehicles, rsus, condition) in done:
            print(f"[{index}/{len(targets)}] already complete V{vehicles} R{rsus} {condition}", flush=True)
            continue
        prefix = f"{args.source_tag}{args.area.title()}V{vehicles}R{rsus}FixedCap"
        ini = GENERATED / f"{prefix}.ini"
        if not ini.exists(): raise RuntimeError(f"Missing static INI: {ini}")
        base = f"{prefix}Verge{suffix[condition]}"
        name = f"{args.study_tag}{args.area.title()}V{vehicles}R{rsus}{condition.title()}"
        command = [sys.executable, str(HERE / "rag_verge_evolve.py"), "--ini", str(ini),
                   "--base-config", base, "--memory-results", *map(str, memory),
                   "--baseline-results", *map(str, baselines), "--train-seeds", *map(str, args.train_seeds),
                   "--test-seeds", *map(str, args.test_seeds), "--provider", args.provider,
                   "--model", args.model, "--name", name]
        print(f"[{index}/{len(targets)}] cross-map RAG V{vehicles} R{rsus} {condition}", flush=True)
        subprocess.run(command, check=True)
        outputs = sorted(GENERATED.glob(f"{name}*.result.json"), key=lambda p: p.stat().st_mtime)
        if not outputs: raise RuntimeError("RAG run did not produce a result JSON")
        completed.append({"vehicles": vehicles, "rsus": rsus, "condition": condition,
                          "result": str(outputs[-1].relative_to(HERE))})
        manifest.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(),
            "study": "Cross-map RAG-VERGE validation", "area": args.area,
            "memoryResults": [str(p.relative_to(HERE)) for p in memory],
            "baselineResults": [str(p.relative_to(HERE)) for p in baselines],
            "trainSeeds": args.train_seeds, "testSeeds": args.test_seeds,
            "targets": targets, "completed": completed}, indent=2) + "\n")
    print(manifest)


if __name__ == "__main__":
    main()
