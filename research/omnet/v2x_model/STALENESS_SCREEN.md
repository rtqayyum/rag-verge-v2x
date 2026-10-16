# Packet-state screening experiment

This is the first go/no-go experiment in `MAJOR_REVISION_PLAN.md`. It is **not**
the paper's final evaluation. It uses one Dubai Downtown mobility realization
to establish whether report age and a simple age-aware dispatch rule matter
enough to justify a larger study.

Historical command (the current runner has additional policies; use the new-tag
replay instructions in `PACKET_TELEMETRY_RESULTS.md` for current execution):

```sh
.venv/bin/python research/omnet/v2x_model/run_stale_screen.py --study-tag StaleGateV2 --vehicles 75 --rsus 4 --seeds 4 --resume
```

The runner builds the model, verifies or creates a versioned SUMO trace,
generates an immutable INI, and executes 80 simulations: 2 task intervals ×
3 report periods × 3 packet-state policies × 4 paired seeds, plus 8 fresh-state
references. It prints overall progress and ETA. An interrupted run can use the
same command; resume is allowed only when the INI, source, and trace hashes
match. Never remove earlier study results to get a run to resume. Use a new
`--study-tag` after changing model or design.

The original screen compares `StaleLeast`, `Power2`, and `AgeAware` at 0.1, 0.5, and
1.0-second report periods, with task intervals of 0.6 and 0.3 seconds. The
75-vehicle trace has a measured mean of about 30 active cars and a peak of 50;
the runner records the exact trace metadata. Four MEC servers share 160 work
units/s. `FreshLeast` reads simulator-internal instantaneous workload and is an
unattainable reference, not a deployable baseline or an upper bound. All
policies receive
identical timestamped UDP queue reports and use the same task and packet seeds
within each paired cell. Their chosen server's report age is measured.

The revised mechanism is `FreshPower2`. It samples two servers as `Power2`,
then adds a criticality-weighted penalty for the age of each sampled queue
report. This preserves randomized diversification while making stale
information explicit in the dispatch score. A focused four-seed confirmation
was originally executed with the following command. Its source/INI hash differs
from today's six-policy runner, so do not resume this historical tag:

```sh
.venv/bin/python research/omnet/v2x_model/run_stale_screen.py \
  --study-tag FreshP2Validation \
  --scenario research/omnet/v2x_model/scenario/dubai/downtown-v75-s1-StaleGateV2-d60-dt0p5 \
  --vehicles 75 --rsus 4 --seeds 4 \
  --task-intervals 0.6 0.3 --report-periods 0.5 1.0 --resume --skip-build
```

This confirmation executes 72 paired simulations and writes its own result
files; it does not overwrite the original `StaleGateV2` screen.

The 72-run count refers to the archived four-policy version. The current
six-policy runner executes 104 runs for the same intervals, periods, and four
seeds. See `PACKET_TELEMETRY_RESULTS.md` for the complete 308-run audit and
the current command with a new study tag. The extra-penalty ablation retains
the base age correction; it does not remove all freshness awareness.

Outputs are saved separately under `scenario/generated/`:

- `StaleGateV2DowntownV75R4_stale_screen_results.json/.csv`: complete per-run
  KPI records and hashes.
- `StaleGateV2DowntownV75R4_stale_screen_summary.csv`: screen-level means and
  between-seed standard deviations.
- `..._completion.png` and `..._pareto.png`: critical completion against report
  period and signaling payload bytes/s.
- `logs/<config>-<seed>.log`: one failure/audit log per simulation.

The primary rate counts all offered critical tasks, including tasks that fail
to return. The study also records ordinary completion, response coverage,
tail latency, offered work, report delivery, selected report age, and signaling
payload bytes. Report bytes are application payload, not full radio-frame
overhead. Dynamic 5G handover is disabled; the initial cell is assigned from
the vehicle's departure-side position. This screen does not establish true
handover performance or superiority over published methods. Those checks
belong to the later confirmatory evaluation.

Before expanding, inspect whether completion varies with report age, whether
the age-aware rule improves the completion-versus-cost tradeoff across paired
seeds, and whether any gain survives the heavier task interval without
unacceptable ordinary-task loss. If the result is weak, revise the mechanism
before running a larger campaign.
