"""Run reference-inspired self-evolution across existing Downtown RAG cells."""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent; GENERATED=HERE/'scenario'/'generated'
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--study-tag',default='RagSelfEvolveV1'); p.add_argument('--vehicles',type=int,nargs='+',default=[75,150]); p.add_argument('--rsus',type=int,nargs='+',default=[2,6,10]); p.add_argument('--conditions',nargs='+',choices=['burst','failure'],default=['burst','failure']); p.add_argument('--generations',type=int,default=3); p.add_argument('--provider',default='ollama'); p.add_argument('--model',default='llama3.1:8b'); p.add_argument('--resume',action='store_true'); a=p.parse_args()
 static=sorted(GENERATED.glob('FinalStaticRadioKpiV1*_results.json')); targets=[(v,r,c) for v in a.vehicles for r in a.rsus for c in a.conditions]; manifest=GENERATED/f'{a.study_tag}_manifest.json'; done=json.loads(manifest.read_text()).get('completed',[]) if a.resume and manifest.exists() else []; keys={(x['vehicles'],x['rsus'],x['condition']) for x in done}; suffix={'burst':'Burst','failure':'Failure'}
 for i,(v,r,c) in enumerate(targets,1):
  if (v,r,c) in keys: print(f'[{i}/{len(targets)}] already complete V{v} R{r} {c}',flush=True); continue
  prefix=f'FinalStaticRadioKpiV1DowntownV{v}R{r}FixedCap'; ini=GENERATED/f'{prefix}.ini'; name=f'{a.study_tag}V{v}R{r}{c.title()}'
  command=[sys.executable,str(HERE/'rag_verge_self_evolve.py'),'--ini',str(ini),'--base-config',f'{prefix}Verge{suffix[c]}','--memory-results',*map(str,static),'--baseline-results',*map(str,static),'--generations',str(a.generations),'--provider',a.provider,'--model',a.model,'--name',name]
  print(f'[{i}/{len(targets)}] self-evolve V{v} R{r} {c}',flush=True); subprocess.run(command,check=True)
  outputs=sorted(GENERATED.glob(f'{name}*.result.json'),key=lambda x:x.stat().st_mtime); done.append({'vehicles':v,'rsus':r,'condition':c,'result':str(outputs[-1].relative_to(HERE))}); manifest.write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),'targets':targets,'completed':done,'generations':a.generations},indent=2)+'\n')
 print(manifest)
if __name__=='__main__': main()
