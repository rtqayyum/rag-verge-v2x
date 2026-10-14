"""Run a checkpointed RAG-VERGE portfolio evaluation on completed static cells.

Each target uses seeds 0--2 for offline policy selection and seeds 3--4 only
for paired evaluation.  Retrieval excludes every static VERGE row from the
target vehicle/RSU/condition cell.  The completed static study is used solely
as a paired held-out comparator.
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
    parser.add_argument("--study-tag", default="RagPortfolioV1")
    parser.add_argument("--vehicles", type=int, nargs="+", default=[75, 150])
    parser.add_argument("--rsus", type=int, nargs="+", default=[2, 6, 10], choices=[2, 4, 6, 8, 10])
    parser.add_argument("--conditions", nargs="+", choices=["nominal", "burst", "failure"],
                        default=["burst", "failure"])
    parser.add_argument("--train-seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--test-seeds", type=int, nargs="+", default=[3, 4])
    parser.add_argument("--provider", choices=["ollama", "openai-compatible"], default="ollama")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--candidate-limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if set(args.train_seeds) & set(args.test_seeds):
        parser.error("train and test seeds must be disjoint")

    static = sorted(GENERATED.glob("FinalStaticRadioKpiV1*_results.json"))
    if len(static) != 20:
        parser.error(f"Expected the 20 completed FinalStaticRadioKpiV1 result files, found {len(static)}")
    suffix = {"nominal": "", "burst": "Burst", "failure": "Failure"}
    targets = [(v, r, c) for v in args.vehicles for r in args.rsus for c in args.conditions]
    manifest = GENERATED / f"{args.study_tag}_manifest.json"
    completed: list[dict] = []
    if args.resume and manifest.exists():
        completed = json.loads(manifest.read_text()).get("completed", [])
    completed_keys = {(x["vehicles"], x["rsus"], x["condition"]) for x in completed}

    for index, (vehicles, rsus, condition) in enumerate(targets, 1):
        key = (vehicles, rsus, condition)
        if key in completed_keys:
            print(f"[{index}/{len(targets)}] already complete V{vehicles} R{rsus} {condition}", flush=True)
            continue
        prefix = f"FinalStaticRadioKpiV1DowntownV{vehicles}R{rsus}FixedCap"
        ini = GENERATED / f"{prefix}.ini"
        if not ini.exists():
            raise RuntimeError(f"Missing completed static scenario INI: {ini}")
        base = f"{prefix}Verge{suffix[condition]}"
        target_name = f"{args.study_tag}V{vehicles}R{rsus}{condition.title()}"
        command = [sys.executable, str(HERE / "rag_verge_evolve.py"),
                   "--ini", str(ini), "--base-config", base,
                   "--memory-results", *map(str, static),
                   "--baseline-results", *map(str, static),
                   "--train-seeds", *map(str, args.train_seeds),
                   "--test-seeds", *map(str, args.test_seeds),
                   "--provider", args.provider, "--model", args.model, "--name", target_name]
        if args.candidate_limit:
            command.extend(["--candidate-limit", str(args.candidate_limit)])
        print(f"[{index}/{len(targets)}] RAG evolve V{vehicles} R{rsus} {condition}", flush=True)
        result = subprocess.run(command, text=True)
        if result.returncode:
            raise RuntimeError(f"RAG target V{vehicles} R{rsus} {condition} failed")
        outputs = sorted(GENERATED.glob(f"{target_name}*.result.json"), key=lambda path: path.stat().st_mtime)
        if not outputs:
            raise RuntimeError(f"RAG target V{vehicles} R{rsus} {condition} produced no result JSON")
        completed.append({"vehicles": vehicles, "rsus": rsus, "condition": condition,
                          "result": str(outputs[-1].relative_to(HERE))})
        manifest.write_text(json.dumps({
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "studyTag": args.study_tag, "targets": targets, "completed": completed,
            "trainSeeds": args.train_seeds, "testSeeds": args.test_seeds,
        }, indent=2) + "\n")
    print(manifest)


if __name__ == "__main__":
    main()
