# V2X edge scheduling experiment

> For the final RAG-VERGE study, use the repository-level [`README.md`](../../../README.md).
> It documents the finalized static and adaptive experiments, their preserved
> result datasets, software versions, and current evaluation limitations.

The remainder of this file records the original small packet-level pilot; its
results are historical and are not the finalized paper dataset.

This experiment joins a SUMO-generated eight-car road trace to INET's
`BonnMotionMobility` and Simu5G's 5G access/core model. Each UE sends UDP
tasks to one of two edge servers. The servers have single-worker FIFO compute
queues; the reply travels back through Simu5G. A task succeeds only when its
reply arrives by its deadline. The model executes headlessly in `Cmdenv`.

## Policies and conditions

| Policy | Rule |
| --- | --- |
| `nearest` | Dispatch to the server associated with the UE's current half of the road. |
| `earliest` | Minimize estimated network delay, queue delay, and service time. |
| `risk` | Add a future-cell/handover penalty and a feedback reliability penalty to the earliest-finish score. |
| `replicate` | Use the risk rule; for critical tasks near the 500 m boundary or with poor primary-server reliability, also send to the alternate if its last observed queue is under 0.35 s. Count the first reply only. |

The 60 s scenario generates tasks from 3 to 53 s at 0.6 s intervals per
vehicle; burst runs use 0.2 s. Critical task probability is 0.35. Critical
and ordinary deadlines are 0.7 and 2 s. Work is uniform from 1 to 2 units;
server rates are 16 and 20 units/s. The outage runs drop requests arriving
at edge 2 during [25, 37) s. Random task streams are paired across policies
for each simulator seed.

## Run

The local `research/omnet/headless` stack must be built first. From the
project root, activate `.venv` and regenerate the mobility trace if desired:

```sh
.venv/bin/python research/omnet/v2x_model/generate_mobility.py --seed 1
```

Build the custom library after code changes:

```sh
bash research/omnet/v2x_model/build.sh
```

The script selects GNU Make when it is available. Run one case or the paired
matrix from the project root:

```sh
bash research/omnet/v2x_model/run.sh RiskFailure 0
.venv/bin/python research/omnet/v2x_model/experiment.py --seeds 20
```

The matrix writes `experiment_results.json` and `.csv`; each run's complete
OMNeT++ scalars are in `scenario/results/`. `overloaded_pilot_results.json`
preserves the earlier experiment with server rates 8 and 10 units/s. Its
"nominal" offered load exceeded combined service capacity and should not be
mixed with the revised experiment.

## Dubai scenario and infrastructure sweeps

`generate_dubai.py` imports a small OpenStreetMap road extract for Downtown
Dubai, Dubai Marina, or a Sheikh Zayed Road corridor, generates reproducible
SUMO traffic, and exports trajectories. `prepare_dubai_ini.py` places 2, 4, or
6 co-located 5G gNB + MEC access points on a documented spatial grid, then
generates all five policy configurations. `run_dubai_experiment.py` runs paired
policy comparisons for that exact map, vehicle set, and access-point layout.

```sh
# 1. Download one controlled map extract and build a 75-vehicle SUMO trace.
.venv/bin/python research/omnet/v2x_model/generate_dubai.py \
  --area downtown --vehicles 75 --seed 1

# 2. Create immutable OMNeT++ configurations for a four-access-point deployment.
.venv/bin/python research/omnet/v2x_model/prepare_dubai_ini.py \
  --scenario research/omnet/v2x_model/scenario/dubai/downtown-v75-s1 \
  --rsus 4 --edge-rate 80 --name DubaiDowntownV75R4

# 3. Five-seed screening sweep: five policies, normal/burst/failure conditions.
.venv/bin/python research/omnet/v2x_model/run_dubai_experiment.py \
  --ini research/omnet/v2x_model/scenario/generated/DubaiDowntownV75R4.ini \
  --prefix DubaiDowntownV75R4 --seeds 5

# 4. After fixing the study design, run the reported 20-seed result.
.venv/bin/python research/omnet/v2x_model/run_dubai_experiment.py \
  --ini research/omnet/v2x_model/scenario/generated/DubaiDowntownV75R4.ini \
  --prefix DubaiDowntownV75R4 --seeds 20
```

The `metadata.json` beside every SUMO trace records the geographic bounding
box, download URL, demand seed, coordinate boundary, route file, and trace.
The generated `.ini` captures access-point locations, server capacities,
vehicle count, policy configurations, and failure timing. Do not use the
screening sweep to make a final performance claim: reserve a held-out map and
scenario seeds for the 20-seed confirmation.

For a fair **RSU-density-only** experiment, hold total MEC capacity constant.
For example, use `--total-edge-rate 320`: each server receives 160 units/s in
the two-RSU case, 80 in the four-RSU case, and about 53.33 in the six-RSU
case. Use `--edge-rate 80` only when studying the operational effect of
deploying an additional complete MEC access point.

## One-command final packet-level screening

The following command builds each cached Dubai trace, creates every scenario,
and runs the complete paired screen. It covers 25, 75, and 150 vehicles with
2, 4, 6, 8, and 10 MEC-enabled roadside access points, under fixed aggregate
capacity. It schedules 1,125 simulations (five policies, three conditions,
five seeds); expect several hours on a laptop.

```sh
.venv/bin/python research/omnet/v2x_model/run_final_packet_study.py \
  --area downtown --vehicles 25 75 150 --rsus 2 4 6 8 10 \
  --total-edge-rate 320 --seeds 5
```

Use `--dry-run` to print the planned commands without running them. The runner
writes `final_packet_study_manifest.json` so the full factorial design remains
explicit. The packet-level model is deliberately capped at ten roadside access
points: its full X2 control mesh grows quadratically. The 20--50 access-point
city-scale phase must use a separately calibrated sparse-control/surrogate
model and be validated against this packet-level screen before results are
combined in a paper.

## Interpretation limits

- This is an offline SUMO trajectory export, not live TraCI-to-OMNeT++ or
  Veins coupling. SUMO seed 1 supplies one road mobility realization for all
  network/task seeds.
- Both servers sit behind a common anchor UPF/router. The policy's
  cross-cell backhaul delay is an *estimated score term*, not a measured
  difference in the packet path to the two servers. These results cannot
  establish a physical handover-aware latency gain.
- Server service rate, failure, and task deadlines are illustrative parameters;
  they have not been calibrated to a deployed edge system. Radio and transport
  are simulated by Simu5G; compute is an abstract queue.
- The `risk` and `replicate` rules are hand-designed. No LLM designs or adapts
  them, and their originality versus published methods has not been
  established. Results are a research pilot, not a journal claim.
- Each task is generated open-loop; this model has no admission control,
  cancellation of duplicate work, multi-tenant traffic, or energy accounting.
