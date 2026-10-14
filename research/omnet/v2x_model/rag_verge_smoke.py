"""Run a leakage-aware RAG + LLM smoke test for the VERGE-V2X policy.

The LLM is deliberately *not* on the per-task path.  It receives retrieved,
historical aggregate outcomes and proposes a small typed VERGE policy profile.
The verifier bounds every value before the profile is written into an immutable
OMNeT++ INI file.  The smoke test then runs paired static-VERGE and RAG-VERGE
cases with the same simulator seed.

This is a functional validation, not final evidence of an LLM gain.  The full
study must evolve only on training scenarios and evaluate only on held-out
map/seed/failure settings.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
POLICY_BOUNDS = {
    "vergeReliabilityTarget": (0.75, 0.99),
    "vergeDelayUncertainty": (0.03, 0.25),
    "handoverRiskPenalty": (0.02, 0.80),
    "failureRiskPenalty": (0.10, 3.00),
    "replicationMaxAlternateQueue": (0.05, 0.60),
    "ragOverloadQueueThreshold": (0.02, 0.60),
}


def read_scalars(path: Path) -> dict[str, float]:
    wanted = {
        "offeredCritical", "offeredOrdinary", "successCritical", "successOrdinary",
        "lateCritical", "lateOrdinary", "unanswered", "responseCount", "replicatedTasks",
        "vergeShieldFallbacks", "vergeSafeReplications", "ragOverloadFallbacks", "totalResponseLatency",
        "totalObservedQueueDelay", "meanDecisionTimeUs", "tasksDroppedFailure",
    }
    totals: dict[str, float] = {}
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0] != "scalar" or not fields[1].startswith("V2XNetwork."):
            continue
        module, metric, value = fields[1], fields[2], fields[3]
        if metric in wanted and (".ue[" in module or ".edge[" in module):
            totals[metric] = totals.get(metric, 0.0) + float(value)
    offered = totals.get("offeredCritical", 0.0)
    totals["criticalCompletionRate"] = totals.get("successCritical", 0.0) / offered if offered else 0.0
    responses = totals.get("responseCount", 0.0)
    totals["meanResponseLatency"] = totals.get("totalResponseLatency", 0.0) / responses if responses else 0.0
    return totals


def scenario_factors(config: str) -> dict[str, Any]:
    match = re.search(r"V(\d+)R(\d+)", config)
    return {
        "vehicles": int(match.group(1)) if match else 0,
        "rsus": int(match.group(2)) if match else 0,
        "condition": "failure" if config.endswith("Failure") else "burst" if config.endswith("Burst") else "nominal",
    }


def load_memory(paths: list[Path], target: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text())
        for row in payload["rows"]:
            # Retain past static VERGE outcomes only.  The target configuration
            # is excluded entirely to prevent evaluation leakage.
            if row.get("policy") != "verge":
                continue
            factors = scenario_factors(row.get("config", ""))
            if factors == target:
                continue
            record = {
                "source": str(path), "config": row.get("config"), "seed": row.get("seed"),
                **factors,
                "criticalCompletionRate": row.get("criticalCompletionRate", 0.0),
                "meanResponseLatency": row.get("meanResponseLatency", 0.0),
                "replicatedTasks": row.get("replicatedTasks", 0.0),
                "vergeShieldFallbacks": row.get("vergeShieldFallbacks", 0.0),
                "tasksDroppedFailure": row.get("tasksDroppedFailure", 0.0),
            }
            distance = (abs(math.log1p(record["vehicles"]) - math.log1p(target["vehicles"]))
                        + abs(record["rsus"] - target["rsus"]) / 4
                        + (0 if record["condition"] == target["condition"] else 3))
            record["retrievalDistance"] = distance
            records.append(record)
    return sorted(records, key=lambda record: record["retrievalDistance"])


def prompt_for(target: dict[str, Any], memories: list[dict[str, Any]]) -> str:
    compact = [{key: value for key, value in record.items() if key not in {"source", "retrievalDistance"}}
               for record in memories]
    return f"""You are evolving a safety-critical V2X edge-scheduling policy.
Target deployment state: {json.dumps(target)}
Retrieved validated historical VERGE outcomes: {json.dumps(compact)}

Return only one JSON object. Propose a conservative profile for this target.
Use exactly these numeric keys and no others: vergeReliabilityTarget,
vergeDelayUncertainty, handoverRiskPenalty, failureRiskPenalty, and
replicationMaxAlternateQueue, and ragOverloadQueueThreshold. Each value must be one scalar number: never a
string, list, range, or object. The inclusive allowed ranges are:
{json.dumps(POLICY_BOUNDS)}
The required output shape is exactly:
{{"vergeReliabilityTarget": 0.90, "vergeDelayUncertainty": 0.08,
 "handoverRiskPenalty": 0.20, "failureRiskPenalty": 1.0,
 "replicationMaxAlternateQueue": 0.35, "ragOverloadQueueThreshold": 0.18}}
Higher reliability target is stricter. Do not write code, explanations, Markdown,
network commands, or task dispatch decisions. The policy will be verified before use.
"""


def call_llm(prompt: str, provider: str, endpoint: str, model: str, key_env: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if provider == "ollama":
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/api/chat",
            data=json.dumps({
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
            }).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            raise RuntimeError(f"Local Ollama request failed ({error.code}): {detail}") from error
        return json.loads(raw["message"]["content"]), {
            "provider": "ollama", "model": model, "endpoint": endpoint,
            "evalCount": raw.get("eval_count"), "promptEvalCount": raw.get("prompt_eval_count"),
        }
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(f"{key_env} is not set. Set it or use --provider ollama for a local LLM smoke test.")
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps({
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        }).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"LLM request failed ({error.code}): {detail}") from error
    content = raw["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(content), {"provider": "openai-compatible", "model": model,
                                 "endpoint": endpoint, "usage": raw.get("usage", {})}


def verify(proposal: dict[str, Any]) -> dict[str, float]:
    if set(proposal) != set(POLICY_BOUNDS):
        raise RuntimeError(f"Proposal must contain exactly {sorted(POLICY_BOUNDS)}; got {sorted(proposal)}")
    verified: dict[str, float] = {}
    for name, (low, high) in POLICY_BOUNDS.items():
        value = proposal[name]
        # Small local models sometimes emit a JSON numeric string despite the
        # prompt. Accept only a complete numeric literal, normalize it, then
        # apply the same finite-range verifier used for native JSON numbers.
        if isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
            value = float(value)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise RuntimeError(f"{name} must be a finite number")
        if not low <= float(value) <= high:
            raise RuntimeError(f"{name}={value} violates verified range [{low}, {high}]")
        verified[name] = float(value)
    return verified


def append_candidate_ini(source: Path, config: str, base_config: str, profile: dict[str, float]) -> Path:
    destination = source.parent / f"{config}.ini"
    lines = [source.read_text(), "\n# Immutable RAG-VERGE candidate generated by rag_verge_smoke.py\n",
             f"[Config {config}]\n", f"extends = {base_config}\n"]
    for name, value in profile.items():
        unit = "s" if name != "vergeReliabilityTarget" else ""
        lines.append(f"*.ue[*].app[0].{name} = {value}{unit}\n")
    # This RAG-specific audit KPI is not present in legacy static INIs.
    lines.append("*.ue[*].app[0].ragOverloadFallbacks.scalar-recording = true\n")
    destination.write_text("".join(lines))
    return destination


def run_case(ini: Path, config: str, seed: int) -> dict[str, float]:
    environment = os.environ.copy()
    environment["V2X_INI"] = str(ini)
    result = subprocess.run(["bash", str(HERE / "run.sh"), config, str(seed)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
    log = ini.parent / "logs" / f"{config}-{seed}.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"{config} failed; inspect {log}")
    return read_scalars(ini.parent / "results" / f"{config}-{seed}.sca")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ini", type=Path, required=True, help="Generated held-out scenario INI.")
    parser.add_argument("--base-config", required=True, help="Static Verge configuration to compare against.")
    parser.add_argument("--memory-results", type=Path, nargs="+", required=True,
                        help="Completed training-scenario *_results.json files; never include held-out target results.")
    parser.add_argument("--seed", type=int, default=0)
    # DeepSeek's hosted API has retired the original Coder-V2 identifier.
    # Use its current JSON-capable model by default; an archived/local
    # Coder-V2 endpoint can be supplied explicitly for reproduction.
    parser.add_argument("--provider", choices=("openai-compatible", "ollama"), default="openai-compatible")
    parser.add_argument("--endpoint", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--name", default="RagVergeSmoke")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source_ini = args.ini.resolve()
    if not source_ini.is_file():
        parser.error(f"INI not found: {source_ini}")
    target = scenario_factors(args.base_config)
    memory = load_memory([path.resolve() for path in args.memory_results], target)
    if len(memory) < args.top_k:
        parser.error(f"Only {len(memory)} non-leaking VERGE records available; need at least --top-k {args.top_k}.")
    retrieved = memory[:args.top_k]
    prompt = prompt_for(target, retrieved)
    print(f"RAG retrieval: {len(retrieved)} records for held-out {target}")
    for record in retrieved:
        print(f"  {record['config']} seed={record['seed']} distance={record['retrievalDistance']:.3f}")
    if args.dry_run:
        print(prompt)
        return
    print(f"Calling {args.model} once for an offline typed policy proposal...", flush=True)
    endpoint = args.endpoint if args.provider == "openai-compatible" else (
        args.endpoint if args.endpoint != "https://api.deepseek.com" else "http://localhost:11434")
    proposal, llm_metadata = call_llm(prompt, args.provider, endpoint, args.model, args.api_key_env)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        profile = verify(proposal)
    except RuntimeError:
        audit = source_ini.parent / f"{args.name}{timestamp}.invalid-proposal.json"
        audit.write_text(json.dumps({"target": target, "retrievedMemory": retrieved,
                                     "llm": llm_metadata, "rawProposal": proposal}, indent=2) + "\n")
        print(f"Rejected LLM proposal saved for audit: {audit}", flush=True)
        raise
    candidate = f"{args.name}{timestamp}"
    candidate_ini = append_candidate_ini(source_ini, candidate, args.base_config, profile)
    print("LLM proposal verified:", json.dumps(profile, sort_keys=True), flush=True)
    print("[1/2] Running paired static VERGE baseline...", flush=True)
    baseline = run_case(source_ini, args.base_config, args.seed)
    print("[2/2] Running RAG-VERGE candidate...", flush=True)
    candidate_result = run_case(candidate_ini, candidate, args.seed)
    output = candidate_ini.with_suffix(".result.json")
    output.write_text(json.dumps({
        "created_utc": datetime.now(timezone.utc).isoformat(), "target": target,
        "baseIni": str(source_ini), "candidateIni": str(candidate_ini), "baseConfig": args.base_config,
        "candidateConfig": candidate, "seed": args.seed, "retrievedMemory": retrieved,
        "llm": llm_metadata, "verifiedProfile": profile, "baseline": baseline,
        "ragVerge": candidate_result,
    }, indent=2) + "\n")
    print(f"Smoke test complete: {output}")


if __name__ == "__main__":
    main()
