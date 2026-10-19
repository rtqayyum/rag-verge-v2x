"""Run a five-policy smoke test for the corrected integrated experiment path."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from generate_dubai import generate
from integrated_common import (BASELINES, HERE, PolicyProfile,
                               prepare_integrated_ini, run_case, source_hash)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-tag", default="IntegratedSmokeV1")
    parser.add_argument("--vehicles", type=int, default=75)
    parser.add_argument("--rsus", type=int, default=4)
    parser.add_argument("--mobility-seed", type=int, default=1)
    parser.add_argument("--scenario", type=Path,
                        help="Existing immutable activity-aware SUMO scenario")
    parser.add_argument("--network-seed", type=int, default=0)
    parser.add_argument("--target-load", type=float, default=0.8)
    parser.add_argument("--report-period", type=float, default=0.5)
    parser.add_argument("--total-edge-rate", type=float, default=160.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    subprocess.run(["bash", str(HERE / "build.sh")], check=True)
    scenario = (args.scenario.resolve() if args.scenario else
                generate("downtown", args.vehicles, args.mobility_seed, 60, 0.5,
                         args.study_tag))
    metadata = json.loads((scenario / "metadata.json").read_text())
    interval = round(1000.0 * metadata["mean_active_vehicles"] * 1.5 / (
        args.total_edge_rate * args.target_load)) / 1000.0
    profile = PolicyProfile(min(3, args.rsus), 1.0, 0.35, 2.0)
    name = f"{args.study_tag}DowntownV{args.vehicles}R{args.rsus}M{args.mobility_seed}"
    ini = prepare_integrated_ini(scenario, args.rsus, args.total_edge_rate, name,
                                 [interval], [args.report_period], [profile])
    output = ini.with_name(name + "_results.json")
    rows: list[dict] = []
    if output.exists():
        if not args.resume:
            raise RuntimeError(f"Smoke output exists; use --resume or a new tag: {output}")
        rows = json.loads(output.read_text())["rows"]
    completed = {row["method"] for row in rows}
    ilabel, plabel = round(interval * 1000), round(args.report_period * 1000)
    methods = list(BASELINES) + ["RAG-VERGE"]
    for index, method in enumerate(methods, 1):
        if method in completed:
            continue
        suffix = (f"Rag{profile.key}" if method == "RAG-VERGE"
                  else f"Control{method}")
        config = f"{name}I{ilabel}P{plabel}{suffix}"
        row = run_case(ini, config, args.network_seed, 60.0, args.total_edge_rate)
        row.update(method=method, profile=(None if method != "RAG-VERGE" else
                                          profile.__dict__), targetLoad=args.target_load,
                   taskIntervalS=interval, reportPeriodS=args.report_period,
                   mobilitySeed=args.mobility_seed)
        rows.append(row)
        output.write_text(json.dumps({
            "manifest": {"studyTag": args.study_tag,
                         "createdUtc": datetime.now(timezone.utc).isoformat(),
                         "sourceSha256": source_hash(), "ini": str(ini),
                         "rngSeparation": {"taskStream": 0, "selectionStream": 1},
                         "deadlineAdmission": True,
                         "deployableState": "packet-delivered reports only",
                         "oracleRole": "diagnostic only"},
            "rows": rows,
        }, indent=2) + "\n")
        print(f"[{index}/{len(methods)}] {method}: critical="
              f"{row['criticalCompletionRate']:.3f}, rejected="
              f"{row['criticalRejectionRate']:.3f}", flush=True)
    print(output)


if __name__ == "__main__":
    main()
