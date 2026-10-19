"""Shared preparation and execution helpers for the integrated RAG-VERGE study.

The integrated design uses only packet-delivered state for deployable methods,
keeps task-generation and randomized-selection RNG streams separate, and
enables deadline admission consistently for every compared policy.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

from prepare_stale_ini import prepare
from run_stale_screen import (EDGE_METRICS, UE_METRICS, report_age_mean,
                              scalar_metrics, vector_metrics)


HERE = Path(__file__).resolve().parent
GENERATED = HERE / "scenario" / "generated"


@dataclass(frozen=True)
class PolicyProfile:
    candidate_sample_size: int
    age_penalty: float
    freshness_penalty: float
    critical_boost: float

    def checked(self, num_servers: int) -> "PolicyProfile":
        if not 2 <= self.candidate_sample_size <= num_servers:
            raise ValueError("candidate_sample_size must be between 2 and num_servers")
        if not 0.0 <= self.age_penalty <= 2.0:
            raise ValueError("age_penalty must be in [0, 2]")
        if not 0.0 <= self.freshness_penalty <= 1.0:
            raise ValueError("freshness_penalty must be in [0, 1]")
        if not 1.0 <= self.critical_boost <= 3.0:
            raise ValueError("critical_boost must be in [1, 3]")
        for value in asdict(self).values():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("profile values must be finite")
        return self

    @property
    def key(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (float(self.candidate_sample_size), self.age_penalty,
                self.freshness_penalty, self.critical_boost)


BASELINES = {
    "ReportedEarliest": "staleleast",
    "Power2": "power2",
    "DahlinAge": "ageaware",
    "OracleDiagnostic": "oracleleast",
}


def prepare_integrated_ini(scenario: Path, rsus: int, total_edge_rate: float,
                           name: str, intervals: list[float], periods: list[float],
                           profiles: list[PolicyProfile], failure: bool = False) -> Path:
    """Create one immutable INI containing common controls and proposed profiles."""
    scaffold_name = name + "IntegratedScaffold"
    scaffold = prepare(scenario, rsus, total_edge_rate, scaffold_name, intervals,
                       periods, fresh_reference=False)
    try:
        content = scaffold.read_text().replace(scaffold_name, name)
    finally:
        scaffold.unlink(missing_ok=True)
    base = GENERATED / f"{name}.ini"
    anchor = f"[Config {name}Base]\n"
    if content.count(anchor) != 1:
        raise RuntimeError("Integrated INI base section not found")
    common = (
        "*.ue[*].app[0].missingReportCost = 1s\n"
        "*.edge[*].app[0].deadlineAdmission = true\n"
    )
    content = content.replace(anchor, anchor + common, 1)
    scalar_rules = "".join(
        [f"*.ue[*].app[0].{metric}.scalar-recording = true\n"
         for metric in sorted(UE_METRICS)] +
        [f"*.edge[*].app[0].{metric}.scalar-recording = true\n"
         for metric in sorted(EDGE_METRICS)]
    )
    disturbance = ""
    if failure:
        disturbance = ("*.edge[1].app[0].failureStart = 25s\n"
                       "*.edge[1].app[0].failureEnd = 37s\n")
    additions: list[str] = []
    for interval in intervals:
        ilabel = round(interval * 1000)
        for period in periods:
            plabel = round(period * 1000)
            for display, policy in BASELINES.items():
                config = f"{name}I{ilabel}P{plabel}Control{display}"
                additions.append(
                    f"\n[Config {config}]\nextends = {name}Base\n"
                    f"*.ue[*].app[0].policy = \"{policy}\"\n"
                    f"*.ue[*].app[0].taskInterval = {interval:.6f}s\n"
                    f"*.edge[*].app[0].stateReportPeriod = {period:.6f}s\n"
                    f"{disturbance}{scalar_rules}"
                )
            for profile in profiles:
                profile.checked(rsus)
                config = f"{name}I{ilabel}P{plabel}Rag{profile.key}"
                additions.append(
                    f"\n[Config {config}]\nextends = {name}Base\n"
                    "*.ue[*].app[0].policy = \"ragvergepacket\"\n"
                    f"*.ue[*].app[0].taskInterval = {interval:.6f}s\n"
                    f"*.edge[*].app[0].stateReportPeriod = {period:.6f}s\n"
                    f"*.ue[*].app[0].candidateSampleSize = {profile.candidate_sample_size}\n"
                    f"*.ue[*].app[0].agePenalty = {profile.age_penalty:.9g}\n"
                    f"*.ue[*].app[0].freshnessPenalty = {profile.freshness_penalty:.9g}\n"
                    f"*.ue[*].app[0].freshnessCriticalBoost = {profile.critical_boost:.9g}\n"
                    f"{disturbance}{scalar_rules}"
                )
    proposed = content + "".join(additions)
    if base.exists() and base.read_text() != proposed:
        raise RuntimeError(f"Refusing to overwrite changed immutable INI: {base}")
    if not base.exists():
        base.write_text(proposed)
    return base


def run_case(ini: Path, config: str, seed: int, duration: float,
             total_edge_rate: float, retain_raw: bool = False) -> dict:
    environment = os.environ.copy()
    environment["V2X_INI"] = str(ini)
    result = subprocess.run(["bash", str(HERE / "run.sh"), config, str(seed)],
                            cwd=HERE.parent.parent.parent, env=environment,
                            text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    logs = ini.parent / "logs"
    logs.mkdir(exist_ok=True)
    (logs / f"{config}-{seed}.log").write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{config} seed {seed} failed; inspect its log")
    raw = ini.parent / "results"
    scalar = raw / f"{config}-{seed}.sca"
    vector = raw / f"{config}-{seed}.vec"
    metrics = scalar_metrics(scalar)
    metrics.update(vector_metrics(vector))
    offered = metrics["offeredCritical"] + metrics["offeredOrdinary"]
    outcomes = sum(metrics[key] for key in (
        "successCritical", "successOrdinary", "rejectedCritical",
        "rejectedOrdinary", "lateCritical", "lateOrdinary", "unanswered"))
    if not math.isclose(offered, outcomes, abs_tol=0.1):
        raise RuntimeError(f"Task accounting failed for {config}: {offered} != {outcomes}")
    admitted = metrics["admittedWorkUnits"]
    if admitted > metrics["offeredWorkUnits"] + 1e-9:
        raise RuntimeError("Admitted work exceeds server-arrival work")
    row = {
        **metrics,
        "seed": seed,
        "config": config,
        "criticalCompletionRate": metrics["successCritical"] / metrics["offeredCritical"]
            if metrics["offeredCritical"] else 0.0,
        "ordinaryCompletionRate": metrics["successOrdinary"] / metrics["offeredOrdinary"]
            if metrics["offeredOrdinary"] else 0.0,
        "criticalRejectionRate": metrics["rejectedCritical"] / metrics["offeredCritical"]
            if metrics["offeredCritical"] else 0.0,
        "ordinaryRejectionRate": metrics["rejectedOrdinary"] / metrics["offeredOrdinary"]
            if metrics["offeredOrdinary"] else 0.0,
        "responseCoverage": metrics["responseCount"] / offered if offered else 0.0,
        "offeredLoadRatio": metrics["totalOfferedWorkUnits"] /
            (total_edge_rate * max(1.0, duration - 10.0)),
        "meanResponseLatencyS": metrics["totalResponseLatency"] / metrics["responseCount"]
            if metrics["responseCount"] else None,
        "meanStateAgeAtDecisionS": report_age_mean(vector),
        "signalingPayloadBytesPerS": (metrics["stateBytesSent"] +
                                      metrics["stateSubscriptionBytesSent"]) / duration,
        "reportDeliveryFraction": metrics["stateReportsReceived"] /
            metrics["stateReportsSent"] if metrics["stateReportsSent"] else 0.0,
    }
    if not retain_raw:
        for path in (scalar, vector, vector.with_suffix(".vci")):
            path.unlink(missing_ok=True)
    return row


def source_hash() -> str:
    digest = hashlib.sha256()
    for relative in (
        "src/TaskApps.cc", "src/TaskPacket.msg", "src/v2x/TaskClient.ned",
        "src/v2x/TaskServer.ned", "prepare_stale_ini.py", "integrated_common.py",
    ):
        digest.update(relative.encode())
        digest.update((HERE / relative).read_bytes())
    return digest.hexdigest()
