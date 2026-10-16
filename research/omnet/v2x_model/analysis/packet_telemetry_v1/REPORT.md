# Packet telemetry analysis, 16 October 2026

Audited 308 run records across four archived studies. All task counts,
offered workload signatures within paired cells, expected run totals, and
archived INI hashes reconcile. Smoke runs are excluded. The original screen
has 80 runs; method validation has 72; the two scaling batches have 78 each.

FreshPower2 has a positive mean difference over Power2 in 9/12
cells. No critical-completion comparison has a Holm-adjusted two-sided exact
paired sign-flip p-value below 0.05. With only 3 or 4 seeds per cell, the
smallest possible two-sided p-values are 0.25 and 0.125. These are descriptive
pilot results, not independent confirmatory evidence: method design followed
the original screen, and the same mobility and seed sets were reused.

## Interpretation and audit qualifications

- 25/4, 75/4, and 150/8 are joint vehicle/server configurations. The 150/8
  point does not isolate vehicle scaling or RSU scaling. The promised full
  4-density by 5-RSU matrix has NOT been completed.
- Reporting period and payload size are controlled; realized transmitted
  payload bytes differ across policies because subscription delivery and
  vehicle activity interact with the packet network. This is a matched
  reporting configuration, not an exact matched-byte budget. The scatter
  plot reports measured cost. Full radio-frame overhead is not recorded.
- FreshPower2 score = 2*baseNetworkDelay + max(0,busyUntil-now) + work/rate
  + (agePenalty + freshnessPenalty*boost)*arrivalProxy*age.
  boost=2 for critical tasks and 1 otherwise; agePenalty=1 and
  freshnessPenalty=0.35. Missing-report queue cost is 1 second.
- `FreshP2NoFreshness` sets ONLY freshnessPenalty=0, retaining agePenalty=1.
  Its plot label is "No extra penalty". `FreshP2NoCritical` sets boost=1.
  Power2 removes all age correction and uses a different missing-report cost.
  Consequently a difference from Power2 cannot isolate the extra penalty.
- The arrivalProxy is an EWMA of positive busy-until increments over report
  spacing, not an unbiased measurement of work arrival rate.
- Queues are FIFO. Criticality changes selection scores; it does not reorder
  the server queue. There is no decision-triggered reporting, expiry admission,
  or new LLM/RAG component in these runs.
- Dynamic handover remains disabled. Reported task latency includes a modeled
  50-ms boundary-crossing charge. Initial UE attachment follows departure position.
- Latency quantiles are conditional on returned tasks. Mean queue delay uses
  all admitted arrivals; it can include work finishing after the horizon.
- One trip seed per vehicle count, 60-second traces, 160 work units/s total.
  Load ratio is an offered-work proxy divided by 50 seconds of total capacity;
  vehicle activity is nonstationary. Exported cars are not simultaneous cars.
- Historical source hashes are preserved. Current source differs across
  study stages, and exact historical source snapshots were not saved for
  every stage. The current checkout must use a new tag when rerunning.

## Figure guide

01: critical completion across report periods, with between-seed SD.
02: twelve paired Power2 differences; each dot is one seed, diamonds are means.
03: ordinary completion and response coverage, alongside critical completion.
04: returned-task p95 latency and all-admitted-arrival queue delay.
05: measured signaling/completion and report-age/completion scatter plots.
06: ablations for 25/4 and 150/8; bars are means, whiskers are SD.
07: original 75/4 screen over 0.1, 0.5, 1.0-second reporting periods.

All plots are exported as PNG and SVG. Summary CSV and paired comparison CSV
preserve study membership. No pooled tasks-as-replicates significance test is used.
