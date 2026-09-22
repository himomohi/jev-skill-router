"""Synthetic request planning for full and explicitly indexed catalogs. No API."""
from __future__ import annotations
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from benchmark_context import DESCRIPTION
from jev_skill_router.config import Config
from jev_skill_router.router import Router


def measure(count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix='jev-scaling-') as directory:
        root = Path(directory)
        for index in range(count):
            path = root / f'workflow-{index:04}'
            path.mkdir()
            (path / 'SKILL.md').write_text(f'---\nname: workflow-{index:04}\ndescription: {DESCRIPTION}\n---\nInspect inputs and validate outputs.\n', encoding='utf-8')
        router = Router(Config(roots=[str(root)]))
        plans = {}
        try:
            for strategy in ('all', 'indexed'):
                router.config.candidate_strategy = strategy
                plan = router.plan('Apply the specialist workflow to the current input.')
                plans[strategy] = {key: plan[key] for key in ('ready', 'rank_requests', 'verification_requests_upper_bound', 'base_requests_upper_bound', 'http_requests_upper_bound', 'http_request_limit', 'retrieval')}
        finally:
            router.close()
    return {'skills': count, 'strategies': plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/scaling-benchmark.json')
    args = parser.parse_args()
    result = {'schema_version': 1, 'method': 'synthetic local fresh-route preflight; short bodies and identical metadata',
              'api_requests': 0, 'credentials_read': False, 'candidate_limit': 64,
              'description_characters': len(DESCRIPTION),
              'limitations': ['Bounds are planned requests, not measured live usage, latency, cost or accuracy.',
                             'Identical metadata intentionally creates cutoff ties; lexical ranking does not establish relevance.',
                             'Indexed mode evaluates only retrieved candidates and can miss useful skills, especially across languages.',
                             'Catalog discovery still scans all files; this bounds provider candidates, not filesystem work.'],
              'results': [measure(count) for count in (200, 500, 2000, 4096)]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
