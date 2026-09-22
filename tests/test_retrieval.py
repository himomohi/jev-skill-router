"""Explicit lexical narrowing must preserve live verification and budget safety."""
import json

import httpx
import pytest

from conftest import RecordedProvider
from jev_skill_router.catalog import Catalog
from jev_skill_router.cli import main
from jev_skill_router.config import Config, RouterError
from jev_skill_router.jev import JevClient
from jev_skill_router.retrieval import MetadataIndex, terms
from jev_skill_router.router import Router


def catalog(make_skill, count=80):
    for i in range(count):
        directory = make_skill(f'workflow-{i:04}', description='Inspect specialist operation inputs and validate outputs.')
    return directory.parent


def test_indexed_plan_bounds_actual_calls_and_keeps_verification(make_skill):
    root = catalog(make_skill)
    cfg = Config(roots=[str(root)], candidate_strategy='indexed', candidate_limit=8)
    provider = RecordedProvider(fit=.1)
    with_client = JevClient(cfg, 'fixture-key', httpx.MockTransport(provider))
    router = Router(cfg, with_client)
    try:
        plan = router.plan('Inspect specialist operation')
        assert not provider.requests
        assert plan['ready'] and plan['retrieval']['considered_skills'] == 8
        assert plan['retrieval']['truncated'] and plan['retrieval']['cutoff_ties'] == 72
        result = router.route('Inspect specialist operation')
        assert result['catalog_size'] == 80 and result['status'] == 'no_match'
        assert not result['selected']
        assert result['http_requests'] <= plan['http_requests_upper_bound']
        ranked = [q['questions']['rank']['criteria'] for q in provider.requests if 'rank' in q['questions']]
        assert sum(len(options) - 1 for options in ranked) == 8
        assert any('fit_0' in q['questions'] for q in provider.requests)
    finally:
        router.close()


def test_default_and_small_indexed_catalog_keep_cross_language_candidates(make_skill):
    root = catalog(make_skill, 20)
    for cfg in (Config(roots=[str(root)]), Config(roots=[str(root)], candidate_strategy='indexed')):
        router = Router(cfg)
        plan = router.plan('다른 언어로 작업해 주세요')
        assert plan['ready'] and plan['retrieval']['considered_skills'] == 20
        assert not plan['retrieval']['index_applied']


def test_zero_overlap_fails_before_credentials_and_never_reads_bodies(make_skill, monkeypatch):
    root = catalog(make_skill, 10)
    for file in root.glob('*/SKILL.md'):
        file.write_text(file.read_text() + '\nbodyonlysecretterm', encoding='utf-8')
    def forbidden():
        pytest.fail('No-overlap retrieval must not read credentials')
    monkeypatch.setattr('jev_skill_router.router.api_key', forbidden)
    router = Router(Config(roots=[str(root)], candidate_strategy='indexed', candidate_limit=8))
    plan = router.plan('bodyonlysecretterm')
    assert not plan['ready'] and 'not a semantic no-match' in plan['reason']
    with pytest.raises(RouterError, match='No Jev request'):
        router.route('bodyonlysecretterm')
    assert router.client is None and not router.cache


def test_index_refreshes_after_metadata_change(make_skill):
    root = catalog(make_skill, 10)
    router = Router(Config(roots=[str(root)], candidate_strategy='indexed', candidate_limit=8))
    assert router.plan('operation')['ready']
    old_index = router._metadata_index[1]
    file = root / 'workflow-0000' / 'SKILL.md'
    file.write_text(file.read_text().replace('specialist', 'astronomy'), encoding='utf-8')
    plan = router.plan('astronomy')
    assert plan['ready'] and plan['retrieval']['considered_skills'] == 1
    assert router._metadata_index[1] is not old_index


def test_unicode_retrieval_and_tie_reporting(make_skill):
    make_skill('korean', description='문서작성 및 데이터변환을 지원합니다.')
    make_skill('english', description='Python debugging and tracebacks.')
    skills = Catalog([str(make_skill('another').parent)]).skills
    index = MetadataIndex(skills.values())
    found = index.search('문서작성해주세요', 1)
    assert skills[found.ids[0]].name == 'korean'
    assert 'python' in terms('ＰＹＴＨＯＮ')
    assert index.search('tracebacks', 1).ids == index.search('tracebacks tracebacks', 1).ids
    with pytest.raises(RouterError):
        index.search('Python', True)


@pytest.mark.parametrize('field,value', [('candidate_limit', True), ('candidate_limit', 7), ('candidate_limit', 513), ('candidate_strategy', []), ('candidate_strategy', 'automatic')])
def test_retrieval_config_validation(field, value):
    with pytest.raises(RouterError):
        Config(**{field: value}).validate()


def test_cli_overrides_do_not_persist_and_setup_preserves_mode(make_skill, tmp_path, capsys):
    root = catalog(make_skill, 10)
    path = tmp_path / 'config.json'
    Config(roots=[str(root)]).save(path)
    original = path.read_bytes()
    assert main(['--config', str(path), 'plan', 'Inspect operation', '--candidate-strategy', 'indexed', '--candidate-limit', '8']) == 0
    assert json.loads(capsys.readouterr().out)['retrieval']['considered_skills'] == 8
    assert path.read_bytes() == original
    Config(roots=[str(root)], mode='offline').save(path)
    assert main(['--config', str(path), 'setup', '--root', str(root)]) == 0
    capsys.readouterr()
    assert Config.load(path).mode == 'offline'
    assert main(['--config', str(path), 'setup', '--root', str(root), '--live']) == 0
    capsys.readouterr()
    assert Config.load(path).mode == 'live'


def test_maximum_default_catalog_is_plannable_with_explicit_index(make_skill):
    root = catalog(make_skill, 4096)
    # Longer metadata reproduces the default all-catalog request cap.
    from pathlib import Path
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('benchmark_context', Path(__file__).parents[1] / 'scripts/benchmark_context.py')
    benchmark = module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    for file in root.glob('*/SKILL.md'):
        file.write_text(file.read_text().replace('Inspect specialist operation inputs and validate outputs.', benchmark.DESCRIPTION), encoding='utf-8')
    router = Router(Config(roots=[str(root)]))
    all_plan = router.plan('Apply specialist workflow')
    assert not all_plan['ready'] and all_plan['base_requests_upper_bound'] > 32
    router.config.candidate_strategy = 'indexed'
    plan = router.plan('Apply specialist workflow')
    assert plan['ready'] and plan['retrieval']['considered_skills'] == 64
    assert plan['base_requests_upper_bound'] == 2
    assert plan['http_requests'] == 0 and router.client is None
