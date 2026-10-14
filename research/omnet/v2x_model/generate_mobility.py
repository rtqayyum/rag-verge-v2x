"""Export SUMO/TraCI road trajectories to INET's BonnMotion trace format.

Each OMNeT++ UE exists throughout the run. Before its SUMO departure and after
its arrival, it is stationary at the corresponding road endpoint. Task apps
should be configured to transmit only during the active travel window.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import sumo
import traci


HERE = Path(__file__).resolve().parent
SUMO_HOME = Path(sumo.SUMO_HOME)
SUMO_BIN = SUMO_HOME / "bin" / "sumo"
NETCONVERT = SUMO_HOME / "bin" / "netconvert"


def generate(seed: int, cars: int, duration: int, step: float) -> Path:
    scenario = HERE / "scenario"
    scenario.mkdir(parents=True, exist_ok=True)
    nodes = scenario / "road.nod.xml"
    edges = scenario / "road.edg.xml"
    network = scenario / "road.net.xml"
    routes = scenario / "vehicles.rou.xml"
    trace = scenario / "sumo.movements"

    nodes.write_text(
        '<nodes><node id="a" x="0" y="0"/><node id="b" x="500" y="0"/>'
        '<node id="c" x="1000" y="0"/></nodes>\n'
    )
    edges.write_text(
        '<edges><edge id="ab" from="a" to="b" numLanes="1" speed="22"/>'
        '<edge id="bc" from="b" to="c" numLanes="1" speed="22"/></edges>\n'
    )
    routes.write_text(
        '<routes><vType id="car" accel="2.6" decel="4.5" length="5" '
        'maxSpeed="20" sigma="0.15"/>'
        '<route id="east" edges="ab bc"/>'
        + "".join(
            f'<vehicle id="v{i}" type="car" route="east" depart="{2*i}" '
            'departSpeed="max"/>'
            for i in range(cars)
        )
        + '</routes>\n'
    )
    subprocess.run(
        [str(NETCONVERT), "-n", str(nodes), "-e", str(edges), "-o", str(network)],
        check=True, capture_output=True, text=True,
    )

    positions: dict[str, list[tuple[float, float, float]]] = {
        f"v{i}": [(0.0, 0.0, 500.0)] for i in range(cars)
    }
    last_x = {f"v{i}": 0.0 for i in range(cars)}
    traci.start(
        [str(SUMO_BIN), "-n", str(network), "-r", str(routes),
         "--step-length", str(step), "--seed", str(seed),
         "--no-warnings", "true", "--no-step-log", "true",
         "--xml-validation", "never", "--quit-on-end", "true"],
        label=f"mobility-{seed}",
    )
    try:
        for _ in range(round(duration / step)):
            traci.simulationStep()
            now = round(float(traci.simulation.getTime()), 6)
            active = set(traci.vehicle.getIDList())
            for vehicle in positions:
                if vehicle in active:
                    last_x[vehicle] = float(traci.vehicle.getPosition(vehicle)[0])
                positions[vehicle].append((now, last_x[vehicle], 500.0))
    finally:
        traci.close()

    with trace.open("w") as out:
        for i in range(cars):
            out.write(" ".join(
                f"{t:.3f} {x:.3f} {y:.3f}"
                for t, x, y in positions[f"v{i}"]
            ) + "\n")
    (scenario / "mobility_metadata.json").write_text(json.dumps({
        "seed": seed, "cars": cars, "duration_s": duration, "step_s": step,
        "coordinate_system": "road x in metres, y offset to 500 m",
        "departure_times_s": [2 * i for i in range(cars)],
        "trace_file": trace.name,
    }, indent=2) + "\n")
    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--cars", type=int, default=8)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--step", type=float, default=0.5)
    arguments = parser.parse_args()
    print(generate(arguments.seed, arguments.cars, arguments.duration, arguments.step))
