"""Opt-in live routing evaluation. Input JSONL: {task, expected:[unique skill names]}.

This makes billed TypeSafe requests and sends tasks + catalog evidence to TypeSafe.
No task text or skill bodies are written into the resulting report.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jev_skill_router.config import Config,RouterError,config_path
from jev_skill_router.router import Router

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset',type=Path)
    parser.add_argument('--config',type=Path,default=config_path())
    parser.add_argument('--allow-live',action='store_true',required=True)
    parser.add_argument('--out',type=Path,default=Path('live-evaluation.json'))
    args=parser.parse_args()
    cfg=Config.load(args.config);cfg.mode='live';cfg.cache_seconds=0
    rows=[json.loads(line) for line in args.dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or len(rows)>200:parser.error('Use between 1 and 200 cases per explicit run.')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('task'),str) or not isinstance(row.get('expected'),list) or not all(isinstance(x,str) for x in row['expected']):
            parser.error('Each case needs task:string and expected:string[].')
    router=Router(cfg);records=[]
    names=[s.name for s in router.catalog.skills.values()]
    if len(names)!=len(set(names)):parser.error('Evaluation requires unique skill names; rename duplicates in the evaluation corpus.')
    for row in rows:
        if not set(row['expected'])<=set(names):parser.error('An expected skill name is absent from the catalog.')
    try:
        for index,row in enumerate(rows):
            started=time.perf_counter()
            try:
                result=router.route(row['task'],row.get('context',''))
                chosen=sorted(s['name'] for s in result['selected'])
                records.append({'case':index,'status':result['status'],'selected':chosen,'correct':chosen==sorted(row['expected']),
                    'seconds':round(time.perf_counter()-started,6),'models':result['models'],'api_calls':result['api_calls'],'usage':result['usage']})
            except RouterError:
                records.append({'case':index,'status':'error','correct':False,'seconds':round(time.perf_counter()-started,6)})
    finally:router.close()
    times=sorted(r['seconds'] for r in records)
    report={'live':True,'cases':len(records),'exact_match_accuracy':sum(r['correct'] for r in records)/len(records),
        'error_count':sum(r['status']=='error' for r in records),'p50_seconds':statistics.median(times),
        'p95_seconds':times[max(0,math.ceil(.95*len(times))-1)],'records':records,
        'warning':'Performance applies only to this dataset, configuration, model versions, and run. No full host-task success evaluation.'}
    args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
