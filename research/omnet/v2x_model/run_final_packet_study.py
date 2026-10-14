"""One-command, reproducible packet-level Dubai screening study.

This runner intentionally limits Simu5G to ten MEC-enabled roadside access
points. Above ten, the current full X2 mesh grows quadratically and would test
control-plane scale rather than the scheduling method. City-scale 20--50 RSU
experiments belong to the calibrated surrogate phase.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent


def execute(command: list[str], dry_run: bool) -> None:
    print("+", " ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", choices=("downtown", "marina", "szr"), default="downtown")
    parser.add_argument("--vehicles", nargs="+", type=int, default=[25, 75, 150])
    parser.add_argument("--rsus", nargs="+", type=int, default=[2, 4, 6, 8, 10],
                        choices=(2, 4, 6, 8, 10))
    parser.add_argument("--seeds", type=int, default=5, choices=range(1, 21))
    parser.add_argument("--total-edge-rate", type=float, default=320.0)
    parser.add_argument("--mobility-seed", type=int, default=1)
    parser.add_argument("--conditions", nargs="*", choices=("nominal", "burst", "failure"),
                        default=["nominal", "burst", "failure"])
    parser.add_argument("--study-tag", default="FinalH40",
                        help="Output/configuration name prefix. Keep a new tag for each model revision.")
    parser.add_argument("--resume", action="store_true",
                        help="Resume checkpointed runs only when their generated INI is identical.")
    parser.add_argument("--retain-raw", action="store_true",
                        help="Keep large raw OMNeT++ files after KPI extraction.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    total_simulations = len(args.vehicles) * len(args.rsus) * args.seeds * 5 * len(args.conditions)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study": "Dubai packet-level VERGE-V2X screening",
        "study_tag": args.study_tag,
        "area": args.area, "vehicles": args.vehicles, "rsus": args.rsus,
        "network_seeds": args.seeds, "mobility_seed": args.mobility_seed,
        "conditions": args.conditions, "total_edge_rate": args.total_edge_rate,
        "simulations": total_simulations,
        "note": "Fixed aggregate capacity isolates RSU density from MEC capacity.",
    }
    output = HERE / "scenario" / "generated" / f"{args.study_tag}_packet_study_manifest.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Planned packet-level simulations: {total_simulations}")
    print(f"Manifest: {output}")
    completed = 0
    wall_start = time.perf_counter()
    result_files: list[Path] = []
    for vehicles in args.vehicles:
        scenario = HERE / "scenario" / "dubai" / f"{args.area}-v{vehicles}-s{args.mobility_seed}"
        execute([sys.executable, str(HERE / "generate_dubai.py"), "--area", args.area,
                 "--vehicles", str(vehicles), "--seed", str(args.mobility_seed)], args.dry_run)
        for rsus in args.rsus:
            name = f"{args.study_tag}{args.area.title()}V{vehicles}R{rsus}FixedCap"
            ini = HERE / "scenario" / "generated" / f"{name}.ini"
            execute([sys.executable, str(HERE / "prepare_dubai_ini.py"), "--scenario", str(scenario),
                     "--rsus", str(rsus), "--total-edge-rate", str(args.total_edge_rate),
                     "--name", name], args.dry_run)
            study_runs = args.seeds * 5 * len(args.conditions)
            execute([sys.executable, str(HERE / "run_dubai_experiment.py"), "--ini", str(ini),
                     "--prefix", name, "--seeds", str(args.seeds), "--conditions", *args.conditions],
                    args.dry_run) if args.dry_run else subprocess.run([
                        sys.executable, str(HERE / "run_dubai_experiment.py"), "--ini", str(ini),
                        "--prefix", name, "--seeds", str(args.seeds), "--conditions", *args.conditions,
                        "--progress-total", str(total_simulations), "--progress-offset", str(completed),
                        *( ["--resume"] if args.resume else [] ),
                        *( ["--retain-raw"] if args.retain_raw else [] ),
                    ], check=True)
            completed += study_runs
            result_files.append(ini.parent / f"{name}_results.json")
            elapsed = time.perf_counter() - wall_start
            print(f"[scenario complete {completed}/{total_simulations} | elapsed "
                  f"{time.strftime('%H:%M:%S', time.gmtime(elapsed))}] {name}", flush=True)
    if not args.dry_run:
        analysis = HERE / "analysis" / f"final_{args.area}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        execute([sys.executable, str(HERE / "analyze_kpis.py"), *(str(path) for path in result_files),
                 "--output", str(analysis)], False)
        print(f"Study complete. KPI table and figures: {analysis}")


if __name__ == "__main__":
    main()
