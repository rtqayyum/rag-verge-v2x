"""Create an immutable OMNeT++ configuration for one Dubai scenario.

Access points use a deterministic spatial grid within the imported road
boundary. They represent co-located 5G gNB + MEC nodes, not IEEE 802.11p
DSRC RSUs. The generated INI retains every input required to reproduce a run.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent


def rsu_sites(boundary: list[float], count: int) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = boundary
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    fractions = [((column + 0.5) / columns, (row + 0.5) / rows)
                 for row in range(rows) for column in range(columns)]
    return [(min_x + fx * (max_x - min_x), min_y + fy * (max_y - min_y))
            for fx, fy in fractions[:count]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True,
                        help="Directory created by generate_dubai.py")
    parser.add_argument("--rsus", type=int, choices=(2, 4, 6, 8, 10), required=True)
    capacity = parser.add_mutually_exclusive_group()
    capacity.add_argument("--edge-rate", type=float,
                          help="Work units per second for each MEC server (default: 80).")
    capacity.add_argument("--total-edge-rate", type=float,
                          help="Fixed aggregate MEC capacity, divided equally across RSUs.")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    metadata = json.loads((args.scenario / "metadata.json").read_text())
    vehicles = metadata["vehicles_exported"]
    sites = rsu_sites(metadata["sumo_coordinate_boundary_m"], args.rsus)
    edge_rate = (args.total_edge_rate / args.rsus if args.total_edge_rate is not None
                 else args.edge_rate if args.edge_rate is not None else 80.0)
    if edge_rate <= 0:
        parser.error("edge capacity must be positive")
    addresses = " ".join(f"edge[{index}]" for index in range(args.rsus))
    rates = " ".join(str(edge_rate) for _ in range(args.rsus))
    xs = " ".join(f"{x:.3f}" for x, _ in sites)
    ys = " ".join(f"{y:.3f}" for _, y in sites)
    min_x, min_y, max_x, max_y = metadata["sumo_coordinate_boundary_m"]
    lines = [
        (HERE / "scenario" / "tasks.ini").read_text(),
        "\n# Generated Dubai experiment manifest\n",
        f"[Config {args.name}Base]\n",
        "extends = Verge\n",
        "*.configurator.config = xmldoc(\"../demo.xml\")\n",
        "*.carrierAggregation.componentCarrier[0].numBands = 100\n",
        # The 80 hysteresis setting reduces rapid cell oscillation in dense
        # Dubai trajectories while retaining ordinary X2 handovers. It also
        # avoids a known stale-bearer race in the Simu5G 1.8 handover path.
        "**.hysteresisFactor = 80\n",
        # Simu5G 1.8's dynamic handover scheduler is unstable under dense
        # SUMO traces. Mobility-induced cell crossings are instead accounted
        # for by TaskClient's explicit, reproducible interruption model.
        "**.dynamicCellAssociation = false\n",
        "**.enableHandover = false\n",
        "*.ue[*].app[0].handoverInterruption = 0.05s\n",
        # Simu5G otherwise records every lower-layer scalar from every UE and
        # gNB. The study consumes only application-level task KPIs below.
        "**.scalar-recording = false\n",
        "*.ue[*].app[0].responseLatency.vector-recording = true\n",
        "*.ue[*].app[0].observedQueueDelay.vector-recording = true\n",
        f"*.numUe = {vehicles}\n",
        f"*.numRsu = {args.rsus}\n",
        f"*.ue[*].mobility.traceFile = \"{metadata['trace']}\"\n",
        "*.ue[*].app[0].startTime = 3s + ancestorIndex(1) * 0.05s\n",
        "*.ue[*].app[0].stopTime = 53s\n",
        f"*.ue[*].app[0].numServers = {args.rsus}\n",
        f"*.ue[*].app[0].serverAddresses = \"{addresses}\"\n",
        f"*.ue[*].app[0].serverRates = \"{rates}\"\n",
        f"*.ue[*].app[0].serverXs = \"{xs}\"\n",
        f"*.ue[*].app[0].serverYs = \"{ys}\"\n",
        f"**.mobility.constraintAreaMinX = {min_x:.3f}m\n",
        f"**.mobility.constraintAreaMaxX = {max_x:.3f}m\n",
        f"**.mobility.constraintAreaMinY = {min_y:.3f}m\n",
        f"**.mobility.constraintAreaMaxY = {max_y:.3f}m\n",
    ]
    # Result-recording patterns apply to a named scalar, not just a module.
    # Use explicit names: wildcard scalar names are not interpreted by OMNeT++.
    ue_scalars = (
        "offeredCritical", "offeredOrdinary", "successCritical", "successOrdinary",
        "lateCritical", "lateOrdinary", "unanswered", "responseCount", "replicatedTasks",
        "vergeShieldFallbacks", "vergeSafeReplications", "crossedCellWhilePending",
        "handoverEvents", "meanResponseLatency", "totalResponseLatency",
        "meanObservedQueueDelay", "totalObservedQueueDelay", "maxObservedQueueDelay",
        "meanDecisionTimeUs",
    )
    edge_scalars = (
        "tasksReceived", "tasksDroppedFailure", "resultsSent", "meanQueueDelay",
        "totalQueueDelay", "maxQueueDelay", "serviceWorkUnits", "estimatedBusyFraction",
    )
    scalar_rules = [f"**.ue[*].app[0].{metric}.scalar-recording = true\n" for metric in ue_scalars]
    scalar_rules += [f"**.ue[*].app[0].selectedServer{index}.scalar-recording = true\n"
                     for index in range(args.rsus)]
    scalar_rules += [f"**.ue[*].app[0].reliabilityServer{index}.scalar-recording = true\n"
                     for index in range(args.rsus)]
    scalar_rules += [f"**.edge[*].app[0].{metric}.scalar-recording = true\n" for metric in edge_scalars]
    for index, (x, y) in enumerate(sites):
        lines += [
            f"*.gnb[{index}].mobility.initialX = {x:.3f}m\n",
            f"*.gnb[{index}].mobility.initialY = {y:.3f}m\n",
            f"*.edge[{index}].app[0].workRate = {edge_rate}\n",
        ]
    # Simu5G associates X2 applications with target cells. The NED full mesh
    # allocates a gNB's gates in peer order *with that gNB itself omitted*.
    # Thus its connection to peer p uses x2ppp[p] below its own index and
    # x2ppp[p-1] above it. The old fixed x2ppp0 address only works for the
    # first peer and caused the eight-RSU sweep to fail on its first handover.
    for index in range(args.rsus):
        peers = [peer for peer in range(args.rsus) if peer != index]
        lines.append(f"*.gnb[{index}].numX2Apps = {len(peers)}\n")
        for app, peer in enumerate(peers):
            target_gate = index if index < peer else index - 1
            lines.append(f"*.gnb[{index}].x2App[{app}].client.connectAddress = \"gnb[{peer}]%x2ppp{target_gate}\"\n")
    lines += [
        "\n# Policy and disturbance configurations derived from the fixed scenario above\n",
    ]
    policy_configs = {
        "Nearest": "nearest", "Earliest": "earliest", "Risk": "risk",
        "Replicate": "replicate", "Verge": "verge",
    }
    for label, policy in policy_configs.items():
        lines += [f"[Config {args.name}{label}]\n", f"extends = {args.name}Base\n",
                  f"*.ue[*].app[0].policy = \"{policy}\"\n", *scalar_rules]
        lines += [f"[Config {args.name}{label}Burst]\n", f"extends = {args.name}{label}\n",
                  "*.ue[*].app[0].taskInterval = 0.2s\n"]
        lines += [f"[Config {args.name}{label}Failure]\n", f"extends = {args.name}{label}\n",
                  "*.edge[1].app[0].failureStart = 25s\n",
                  "*.edge[1].app[0].failureEnd = 37s\n"]
    generated = HERE / "scenario" / "generated"
    generated.mkdir(exist_ok=True)
    output = generated / f"{args.name}.ini"
    output.write_text("".join(lines))
    print(output)


if __name__ == "__main__":
    main()
