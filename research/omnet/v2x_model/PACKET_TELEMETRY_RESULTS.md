# Completed packet-telemetry experiments

This is a follow-up to the archived RAG-VERGE study, using activity-aware
SUMO traces and timestamped UDP queue reports. The fixed-policy follow-up
does not make an LLM/RAG benefit claim.

Four datasets contain **308 completed simulations**:

| Study tag | Exported cars / servers | Runs | Seeds | Role |
|---|---:|---:|---:|---|
| StaleGateV2 | 75 / 4 | 80 | 4 | Original staleness screen |
| FreshP2Validation | 75 / 4 | 72 | 4 | Exploratory method comparison |
| FinalFreshP2V25R4 | 25 / 4 | 78 | 3 | Joint configuration check and ablations |
| FinalFreshP2V150R8 | 150 / 8 | 78 | 3 | Joint configuration check and ablations |

The word `Final` in study IDs is historical naming. A full factorial scale
study, independent mobility replications, and literature-method reproductions
have **not** been completed. The mean active populations are 9.93, 29.58, and
54.61 respectively; exported counts do not denote simultaneous active cars.

## Analyze the archived results

From the repository root, using Python with matplotlib and numpy:

```sh
python3 research/omnet/v2x_model/analyze_packet_telemetry.py
```

The script checks complete run counts, unique keys, task-outcome accounting,
equal offered counts and work within paired cells, telemetry delivery, and
archived INI hashes. It creates `analysis/packet_telemetry_v1/` containing:

- `REPORT.md` and `provenance.json`: interpretation, input hashes, limitations.
- `per_run.csv`, `summary.csv`, `paired_comparisons.csv`: all observations,
  study-specific summaries, and exploratory paired comparisons.
- Seven PNG/SVG plot sets covering completion, seed effects, ordinary tasks,
  coverage, returned-task tail latency, admitted-arrival queue wait, report
  age, signaling payload, and ablations.
- `scaling_source_snapshot.zip`: the nine source files whose combined hash
  exactly matches the two scaling-study manifests. This is a source snapshot,
  not a bundled installation of the simulator dependencies.

FreshPower2 improves the mean over Power2 in nine of twelve cells, but the
gain varies and reverses in three cells. All Holm-adjusted exact paired
sign-flip p-values are 1. Three or four seeds cannot establish superiority.
The extra freshness and criticality penalties have no consistent separately
established incremental benefit. See the report before using these plots.

## Run the current model

Install the dependencies documented in the root README and build the model.
Use a **new study tag**: historical INIs and source hashes are immutable.
The current runner includes six deployable policy/ablation configurations
plus the instantaneous-state reference; with the command below it performs
104 runs, whereas the historical 75/4 validation had four policies and 72.

```sh
bash research/omnet/v2x_model/build.sh
python3 research/omnet/v2x_model/run_stale_screen.py \
  --study-tag FreshP2ReplayV1 \
  --scenario research/omnet/v2x_model/scenario/dubai/downtown-v75-s1-StaleGateV2-d60-dt0p5 \
  --area downtown --vehicles 75 --rsus 4 --seeds 4 \
  --task-intervals 0.6 0.3 --report-periods 0.5 1.0 \
  --resume --retain-raw --skip-build
```

The study-tagged INI, logs, JSON/CSV checkpoints, and manifests are separate
for every run design. Resume succeeds only when recorded hashes match.
Keep `--retain-raw` for future audit runs; historical batches retained compact
scalars and latency quantiles, not per-task latency samples. Historical
stage-specific source snapshots were not saved for every earlier screen.

## Policy semantics

- `Power2`: uniform two-server sample, age-uncorrected residual queue score.
- `FreshPower2`: same random sample, base age correction plus an extra
  criticality-weighted report-age/workload-growth-proxy penalty.
- `FreshP2NoFreshness`: removes the **extra** penalty only; the base age
  correction remains. Plot label: "No extra penalty".
- `FreshP2NoCritical`: removes the extra criticality multiplier.
- `StaleLeast` and `AgeAware`: corresponding all-server selection controls.
- `FreshLeast`: internal instantaneous-state reference, not a deployable
  control or a bound. Periodic telemetry still runs in its network scenario.

All deployable controls have matched reporting periods and payload sizes.
Actual transmitted payload varies slightly with delivered subscriptions;
it is not an exact matched-byte budget. Full radio overhead is unmeasured.
The initial attachment follows departure position; dynamic handover is off.
Latency includes the modeled 50-ms boundary-crossing charge. Queues are FIFO.
These batches include no decision-triggered refresh, new LLM search, or
faithful reimplementations of the literature methods.
