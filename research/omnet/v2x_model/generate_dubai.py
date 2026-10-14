"""Build a reproducible Dubai OpenStreetMap/SUMO trace for OMNeT++.

The output records all geographic and random-demand inputs in metadata.json.
The script deliberately uses a small map extract: larger OSM areas generate
unmanageable random traffic and make comparisons less controlled.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

import sumo
import traci


HERE = Path(__file__).resolve().parent
SUMO_HOME = Path(sumo.SUMO_HOME)
AREAS = {
    # west, south, east, north; controlled 2-3 km urban study areas
    "downtown": (55.2700, 25.1850, 55.2900, 25.2050),
    "marina": (55.1300, 25.0700, 55.1500, 25.0900),
    "szr": (55.2500, 25.1550, 55.2750, 25.1800),
}


def command(*items: str) -> None:
    subprocess.run(list(items), check=True)


def generate(area: str, vehicles: int, seed: int, duration: int, step: float) -> Path:
    if vehicles < 2:
        raise ValueError("--vehicles must be at least 2")
    west, south, east, north = AREAS[area]
    output = HERE / "scenario" / "dubai" / f"{area}-v{vehicles}-s{seed}"
    output.mkdir(parents=True, exist_ok=True)
    osm = output / "map.osm.xml"
    cache = HERE / "scenario" / "dubai" / "_maps" / f"{area}.osm.xml"
    network = output / "map.net.xml"
    routes = output / "routes.rou.xml"
    trace = output / "sumo.movements"
    metadata = output / "metadata.json"

    # Overpass ordering is south, west, north, east (unlike our metadata's
    # explicit west, south, east, north order).
    endpoints = ("https://overpass-api.de/api/map", "https://overpass.kumi.systems/api/map")
    query = f"bbox={south},{west},{north},{east}"
    osm_url = f"{endpoints[0]}?{query}"
    cache.parent.mkdir(exist_ok=True)
    if not osm.exists() or osm.stat().st_size == 0:
        if cache.exists() and cache.stat().st_size > 0:
            shutil.copyfile(cache, osm)
        else:
            last_error: Exception | None = None
            for endpoint in endpoints:
                request = urllib.request.Request(f"{endpoint}?{query}", headers={
                    "User-Agent": "VERGE-V2X-research-scenario/0.1 (academic SUMO experiment)"
                })
                try:
                    with urllib.request.urlopen(request, timeout=120) as response:
                        cache.write_bytes(response.read())
                    shutil.copyfile(cache, osm)
                    break
                except urllib.error.URLError as error:
                    last_error = error
            else:
                raise RuntimeError(f"Could not download the OSM extract: {last_error}")
    if not cache.exists() and osm.exists() and osm.stat().st_size > 0:
        shutil.copyfile(osm, cache)
    command(str(SUMO_HOME / "bin" / "netconvert"), "--osm-files", str(osm),
            "--output-file", str(network), "--geometry.remove", "true",
            "--ramps.guess", "true", "--junctions.join", "true")
    period = duration / vehicles
    command(sys.executable, str(SUMO_HOME / "tools" / "randomTrips.py"),
            "-n", str(network), "-r", str(routes), "-b", "0", "-e", str(duration),
            "-p", str(period), "--seed", str(seed), "--vehicle-class", "passenger",
            "--random-departpos", "--random-arrivalpos")

    vehicle_ids = [v.attrib["id"] for v in ET.parse(routes).getroot().findall("vehicle")]
    if len(vehicle_ids) < vehicles:
        raise RuntimeError(f"SUMO produced only {len(vehicle_ids)} valid routes for {vehicles} requested vehicles")
    vehicle_ids = vehicle_ids[:vehicles]
    net_root = ET.parse(network).getroot()
    boundary = [float(value) for value in net_root.find("location").attrib["convBoundary"].split(",")]
    min_x, min_y, max_x, max_y = boundary
    center = ((min_x + max_x) / 2, (min_y + max_y) / 2)
    # A UE must have a distinct position before its SUMO departure. Assigning
    # every future vehicle to the map centre causes an artificial association
    # storm when many cars start at once. Missing positions are backfilled with
    # that vehicle's first observed route position after the SUMO run.
    positions: dict[str, list[tuple[float, float | None, float | None]]] = {
        vehicle: [(0.0, None, None)] for vehicle in vehicle_ids
    }
    last: dict[str, tuple[float, float] | None] = {vehicle: None for vehicle in vehicle_ids}
    label = f"dubai-{area}-{vehicles}-{seed}"
    traci.start([str(SUMO_HOME / "bin" / "sumo"), "-n", str(network), "-r", str(routes),
                 "--step-length", str(step), "--seed", str(seed), "--no-warnings", "true",
                 "--no-step-log", "true", "--xml-validation", "never"], label=label)
    try:
        for _ in range(round(duration / step)):
            traci.simulationStep()
            now = round(float(traci.simulation.getTime()), 6)
            active = set(traci.vehicle.getIDList())
            for vehicle in vehicle_ids:
                if vehicle in active:
                    last[vehicle] = traci.vehicle.getPosition(vehicle)
                if last[vehicle] is None:
                    positions[vehicle].append((now, None, None))
                else:
                    positions[vehicle].append((now, *last[vehicle]))
    finally:
        traci.close()

    with trace.open("w") as stream:
        for vehicle in vehicle_ids:
            first = next(((x, y) for _, x, y in positions[vehicle] if x is not None), center)
            stream.write(" ".join(
                f"{t:.3f} {(x if x is not None else first[0]):.3f} {(y if y is not None else first[1]):.3f}"
                for t, x, y in positions[vehicle]
            ) + "\n")
    metadata.write_text(json.dumps({
        "city": "Dubai", "area": area, "osm_bbox_west_south_east_north": [west, south, east, north],
        "osm_url": osm_url, "vehicles_requested": vehicles, "vehicles_exported": len(vehicle_ids),
        "sumo_seed": seed, "duration_s": duration, "step_s": step,
        "sumo_coordinate_boundary_m": boundary,
        "network": network.relative_to(HERE / "scenario").as_posix(),
        "routes": routes.relative_to(HERE / "scenario").as_posix(),
        "trace": trace.relative_to(HERE / "scenario").as_posix(),
    }, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", choices=AREAS, default="downtown")
    parser.add_argument("--vehicles", type=int, default=75)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--step", type=float, default=0.5)
    args = parser.parse_args()
    print(generate(args.area, args.vehicles, args.seed, args.duration, args.step))
