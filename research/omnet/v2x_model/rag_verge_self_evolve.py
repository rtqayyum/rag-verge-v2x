"""Reference-inspired LLM self-evolution for the verified RAG-VERGE policy.

Unlike the earlier fixed-mutant search, every generation asks the local LLM to
reflect on measured simulator fitness and revise its parent profile.  The LLM
remains offline: OMNeT++ executes only verified numeric profiles.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rag_verge_evolve import run, score, static_baselines, summary
from rag_verge_smoke import (POLICY_BOUNDS, append_candidate_ini, call_llm,
                             load_memory, prompt_for, scenario_factors, verify)


def reflection_prompt(target: dict, parent: dict, fitness: dict, memory: list[dict]) -> str:
    return f"""You are improving a verified V2X edge-scheduling policy offline.
Target: {json.dumps(target)}
Retrieved historical evidence: {json.dumps(memory[:8])}
Current parent profile: {json.dumps(parent)}
Measured training outcome: {json.dumps(fitness)}
Improve critical deadline completion first, then reduce mean response latency and replication.
Return only one JSON object with exactly these numeric keys: {list(POLICY_BOUNDS)}.
Allowed inclusive ranges: {json.dumps(POLICY_BOUNDS)}.
Do not return prose, code, or Markdown."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ini', type=Path, required=True)
    parser.add_argument('--base-config', required=True)
    parser.add_argument('--memory-results', type=Path, nargs='+', required=True)
    parser.add_argument('--baseline-results', type=Path, nargs='+', required=True)
    parser.add_argument('--train-seeds', type=int, nargs='+', default=[0, 1, 2])
    parser.add_argument('--test-seeds', type=int, nargs='+', default=[3, 4])
    parser.add_argument('--generations', type=int, default=3)
    parser.add_argument('--provider', choices=['ollama', 'openai-compatible'], default='ollama')
    parser.add_argument('--model', default='llama3.1:8b')
    parser.add_argument('--endpoint', default='http://localhost:11434')
    parser.add_argument('--api-key-env', default='DEEPSEEK_API_KEY')
    parser.add_argument('--name', default='RagSelfEvolve')
    args = parser.parse_args()
    if set(args.train_seeds) & set(args.test_seeds): parser.error('train and test seeds must be disjoint')
    source = args.ini.resolve(); target = scenario_factors(args.base_config)
    memory = load_memory([p.resolve() for p in args.memory_results], target)
    if len(memory) < 12: parser.error('insufficient non-leaking RAG records')
    baselines = static_baselines([p.resolve() for p in args.baseline_results], target, args.test_seeds)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    proposal, metadata = call_llm(prompt_for(target, memory[:12]), args.provider, args.endpoint, args.model, args.api_key_env)
    parent = verify(proposal); candidates=[]
    for generation in range(args.generations):
        name=f'{args.name}{stamp}G{generation}'
        ini=append_candidate_ini(source, name, args.base_config, parent)
        with ini.open('a') as stream: stream.write('*.ue[*].app[0].policy = "ragverge"\n')
        values=[run(ini,name,seed) for seed in args.train_seeds]
        record={'generation':generation,'candidate':name,'profile':parent,'training':values,'trainingSummary':summary(values),'trainingScore':score(values),'ini':str(ini)}
        candidates.append(record)
        print(f'generation {generation + 1}/{args.generations} score={record["trainingScore"]:.4f}',flush=True)
        if generation + 1 < args.generations:
            revised, _ = call_llm(reflection_prompt(target,parent,record['trainingSummary'],memory),args.provider,args.endpoint,args.model,args.api_key_env)
            parent=verify(revised)
    winner=max(candidates,key=lambda x:x['trainingScore'])
    held=[run(Path(winner['ini']),winner['candidate'],seed) for seed in args.test_seeds]
    candidate_summary=summary(held); base_summary={p:summary(v) for p,v in baselines.items()}
    deltas={p:{'criticalCompletionRate':candidate_summary['criticalCompletionRate']-s['criticalCompletionRate'],
               'meanResponseLatency':candidate_summary['meanResponseLatency']-s['meanResponseLatency'],
               'selectionScore':candidate_summary['selectionScore']-s['selectionScore']} for p,s in base_summary.items()}
    output=source.parent/f'{args.name}{stamp}.result.json'
    output.write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),'target':target,'baseConfig':args.base_config,
        'retrievedMemory':memory[:12],'llm':metadata,'generations':candidates,'winner':winner,'testSeeds':args.test_seeds,
        'heldOut':held,'heldOutSummary':candidate_summary,'staticHeldOutSummary':base_summary,'pairedDeltaVsStatic':deltas},indent=2)+'\n')
    print(f'winner={winner["candidate"]} held-out-score={candidate_summary["selectionScore"]:.4f}')
    print(output)

if __name__=='__main__': main()
