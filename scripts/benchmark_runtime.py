"""Measure real local catalog refresh I/O; no API or model quality simulation."""
from __future__ import annotations
import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jev_skill_router.catalog import Catalog, STAT_CACHE_SUPPORTED


def measure(roots, runs):
    catalog=Catalog(roots)
    results={'full_refresh':[], 'incremental_refresh':[]}
    # Alternate to reduce order and operating-system page-cache bias.
    for repeat in range(runs):
        order=(False,True) if repeat%2 else (True,False)
        for force in order:
            started=time.perf_counter()
            catalog.refresh(force=force)
            results['full_refresh' if force else 'incremental_refresh'].append({
                'seconds':round(time.perf_counter()-started,6), **catalog.refresh_stats})
    return {
        'scope':'Local catalog refresh only; same implementation with force=True versus incremental reuse. Not an old-release or live API benchmark.',
        'platform':platform.system(), 'python':platform.python_version(),
        'catalog_size':len(catalog.skills), 'stat_cache_supported':STAT_CACHE_SUPPORTED,
        'runs_per_mode':runs, 'model_calls':0,
        'median_seconds':{name:statistics.median(row['seconds'] for row in rows) for name,rows in results.items()},
        'samples':results,
        'limitations':['Directory traversal and file stat checks remain.', 'OS caches and filesystem affect timing.', 'Windows reuse requires native NTFS/ReFS change metadata; unsupported or failed queries use full reads. Inspect files_reused for actual behavior.', 'Does not measure selection quality, network time, cost, or complete task success.'],
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--root',action='append')
    source.add_argument('--synthetic-skills',type=int)
    parser.add_argument('--runs',type=int,default=5)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if not 1<=args.runs<=20: parser.error('--runs must be between 1 and 20')
    with tempfile.TemporaryDirectory(prefix='jev-runtime-') as temporary:
        if args.synthetic_skills is not None:
            if not 1<=args.synthetic_skills<=4096: parser.error('Use 1 to 4096 synthetic skills')
            for index in range(args.synthetic_skills):
                directory=Path(temporary)/f'skill-{index:04d}';directory.mkdir()
                (directory/'SKILL.md').write_text(f'---\nname: skill-{index:04d}\ndescription: Public synthetic catalog refresh fixture.\n---\n'+('Read inputs and verify outputs.\n'*80),encoding='utf-8')
            roots=[temporary]
        else:
            roots=args.root
        report=measure(roots,args.runs)
        report['dataset']='synthetic' if args.synthetic_skills is not None else 'provided local roots (paths omitted)'
    text=json.dumps(report,indent=2)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(text,encoding='utf-8')
    print(text,end='')


if __name__=='__main__': main()
