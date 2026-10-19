"""Build a paired packet-telemetry screening INI without touching archived runs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from prepare_dubai_ini import rsu_sites


HERE = Path(__file__).resolve().parent
POLICIES = {
    "StaleLeast": "staleleast",
    "Power2": "power2",
    "AgeAware": "ageaware",
    "FreshPower2": "freshpower2",
    "FreshP2NoFreshness": ("freshpower2", {"freshnessPenalty": 0.0}),
    "FreshP2NoCritical": ("freshpower2", {"freshnessCriticalBoost": 1.0}),
}


def label_ms(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    if milliseconds <= 0 or abs(milliseconds / 1000 - seconds) > 1e-8:
        raise ValueError("Intervals and periods must be positive whole milliseconds")
    return str(milliseconds)


def prepare(scenario: Path, rsus: int, total_edge_rate: float, name: str,
            intervals: list[float], periods: list[float], fresh_reference: bool = True) -> Path:
    scenario = scenario.resolve()
    metadata = json.loads((scenario / "metadata.json").read_text())
    if "active_windows_s" not in metadata or "sha256" not in metadata:
        raise ValueError("Scenario must be an immutable activity-aware SUMO trace")
    if len(metadata["active_windows_s"]) != metadata["vehicles_exported"]:
        raise ValueError("Activity windows do not match exported vehicles")
    if rsus < 3:
        raise ValueError("Power-of-two screening needs at least three MEC servers")
    generated = HERE / "scenario" / "generated"
    raw_name = name + "RawTemplate"
    subprocess.run([sys.executable, str(HERE / "prepare_dubai_ini.py"),
                    "--scenario", str(scenario), "--rsus", str(rsus),
                    "--total-edge-rate", str(total_edge_rate), "--name", raw_name],
                   check=True, capture_output=True, text=True)
    raw = generated / f"{raw_name}.ini"
    try:
        content = raw.read_text().replace(raw_name, name)
    finally:
        raw.unlink(missing_ok=True)
    starts: list[str] = []
    stops: list[str] = []
    active_clients = 0
    duration = float(metadata["duration_s"])
    sites = rsu_sites(metadata["sumo_coordinate_boundary_m"], rsus)
    trace = HERE / "scenario" / metadata["trace"]
    trajectory_lines = trace.read_text().splitlines()
    if len(trajectory_lines) != metadata["vehicles_exported"]:
        raise ValueError("Mobility trace line count does not match exported vehicles")
    initial_cells: list[str] = []
    for index, (first, last) in enumerate(metadata["active_windows_s"]):
        initial = trajectory_lines[index].split()
        x, y = float(initial[1]), float(initial[2])
        nearest = min(range(rsus), key=lambda j: (x - sites[j][0]) ** 2 + (y - sites[j][1]) ** 2)
        # Simu5G NR cell IDs in this network start at 1. With dynamic handover
        # disabled, at least attach each UE to its actual departure-side cell.
        initial_cells.append(f"*.ue[{index}].nrServingNodeId = {nearest + 1}\n")
        start = max(3.0, float(first)) if first is not None else duration + 1.0
        stop = min(duration - 7.0, float(last)) if last is not None else duration + 1.0
        if stop <= start + 0.1:
            start = stop = duration + 1.0
        else:
            active_clients += 1
        starts.append(f"*.ue[{index}].app[0].startTime = {start:.3f}s\n")
        stops.append(f"*.ue[{index}].app[0].stopTime = {stop:.3f}s\n")
    old_start = "*.ue[*].app[0].startTime = 3s + ancestorIndex(1) * 0.05s\n"
    old_stop = "*.ue[*].app[0].stopTime = 53s\n"
    if content.count(old_start) != 1 or content.count(old_stop) < 2:
        raise RuntimeError("Base INI format changed; activity override was not applied")
    base_start = content.index(old_start)
    content = content[:base_start] + content[base_start:].replace(old_start, "".join(starts), 1)
    base_stop = content.index(old_stop, base_start)
    content = content[:base_stop] + content[base_stop:].replace(old_stop, "".join(stops), 1)
    scalars = (
        "offeredCritical", "offeredOrdinary", "totalOfferedWorkUnits",
        "successCritical", "successOrdinary", "rejectedCritical", "rejectedOrdinary",
        "lateCritical", "lateOrdinary", "unanswered", "responseCount",
        "totalResponseLatency", "meanDecisionTimeUs", "stateReportsReceived",
        "stateReportsOutOfOrder", "stateDecisionsWithReport",
        "stateDecisionsWithoutReport", "stateSubscriptionsSent", "stateBytesReceived",
        "stateSubscriptionBytesSent", "meanStateAgeAtDecision",
    )
    server_scalars = (
        "tasksReceived", "tasksDroppedFailure", "tasksRejectedDeadline", "resultsSent",
        "totalQueueDelay", "offeredWorkUnits", "serviceWorkUnits", "admittedWorkUnits",
        "stateReportsSent", "stateBytesSent",
        "stateSubscriptionsReceived",
    )
    additions = [
        f"sim-time-limit = {duration:g}s\n",
        *initial_cells,
        "*.ue[*].app[0].packetTelemetry = true\n",
        "*.edge[*].app[0].packetTelemetry = true\n",
        # Keep randomized server sampling on RNG 1 so it cannot perturb the
        # paired task criticality/work stream on RNG 0.
        "*.ue[*].app[0].rng-1 = 1\n",
        "*.ue[*].app[0].stateAgeAtDecision.vector-recording = true\n",
        f"# Vehicles capable of generating at least one task: {active_clients}\n",
    ]
    # Derived policy sections must carry the named scalar rules. In OMNeT++
    # the Base section's preceding **.scalar-recording=false wins otherwise.
    scalar_rules = "".join(
        [f"*.ue[*].app[0].{metric}.scalar-recording = true\n" for metric in scalars] +
        [f"*.edge[*].app[0].{metric}.scalar-recording = true\n"
         for metric in server_scalars]
    )
    marker = "\n# Policy and disturbance configurations derived from the fixed scenario above\n"
    if content.count(marker) != 1:
        raise RuntimeError("Base INI format changed; no insertion point found")
    content = content.replace(marker, "".join(additions) + marker)
    for interval in intervals:
        load = f"I{label_ms(interval)}"
        for period in periods:
            report = f"P{label_ms(period)}"
            for title, policy_spec in POLICIES.items():
                if isinstance(policy_spec, tuple):
                    policy, overrides = policy_spec
                else:
                    policy, overrides = policy_spec, {}
                config = f"{name}{load}{report}{title}"
                override_lines = "".join(
                    f"*.ue[*].app[0].{parameter} = {value:g}\n"
                    for parameter, value in overrides.items())
                content += (f"\n[Config {config}]\nextends = {name}Base\n"
                            f"*.ue[*].app[0].policy = \"{policy}\"\n"
                            f"*.ue[*].app[0].taskInterval = {interval:g}s\n"
                            f"*.edge[*].app[0].stateReportPeriod = {period:g}s\n"
                            + override_lines
                            + scalar_rules)
        if fresh_reference:
            reference_period = periods[len(periods) // 2]
            content += (f"\n[Config {name}{load}FreshLeast]\nextends = {name}Base\n"
                        "*.ue[*].app[0].policy = \"oracleleast\"\n"
                        f"*.ue[*].app[0].taskInterval = {interval:g}s\n"
                        f"*.edge[*].app[0].stateReportPeriod = {reference_period:g}s\n"
                        + scalar_rules)
    output = generated / f"{name}.ini"
    if output.exists() and output.read_text() != content:
        raise RuntimeError(f"Refusing to overwrite changed immutable INI: {output}")
    if not output.exists():
        output.write_text(content)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--rsus", type=int, default=4)
    parser.add_argument("--total-edge-rate", type=float, default=160.0)
    parser.add_argument("--name", required=True)
    parser.add_argument("--task-intervals", nargs="+", type=float, default=[0.6, 0.3])
    parser.add_argument("--report-periods", nargs="+", type=float, default=[0.1, 0.5, 1.0])
    args = parser.parse_args()
    print(prepare(args.scenario, args.rsus, args.total_edge_rate, args.name,
                  args.task_intervals, args.report_periods))
