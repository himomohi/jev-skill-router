"""The public preflight must predict actual bounds without provider access."""
import json

import httpx
import pytest

from conftest import RecordedProvider
from jev_skill_router.cli import main
from jev_skill_router.config import Config, RouterError
from jev_skill_router.jev import JevClient
from jev_skill_router.router import Router


@pytest.fixture
def forbid_credentials(monkeypatch):
    def forbidden():
        pytest.fail('Local planning must not read credentials')
    monkeypatch.setattr('jev_skill_router.router.api_key', forbidden)


def test_plan_matches_fresh_route_and_does_not_populate_cache(skill_root, forbid_credentials):
    cfg = Config(roots=[str(skill_root)])
    provider = RecordedProvider()
    router = Router(cfg)
    try:
        plan = router.plan('Debug Python')
        assert plan['ready'] and plan['rank_requests'] == 1
        assert plan['verification_requests_upper_bound'] == 1
        assert plan['base_requests_upper_bound'] == 2
        assert plan['http_requests'] == 0 and plan['credentials_checked'] is False
        assert router.client is None and not router.cache
        router.client = JevClient(cfg, 'fixture-key', httpx.MockTransport(provider))
        result = router.route('Debug Python')
        assert result['api_calls'] <= plan['base_requests_upper_bound']
        assert result['http_requests'] <= plan['http_requests_upper_bound']
        count = len(provider.requests)
        assert router.plan('Debug Python')['base_requests_upper_bound'] == 2
        assert len(provider.requests) == count  # A fresh-route plan, even on a cache hit.
    finally:
        router.close()


def test_over_budget_plan_and_route_fail_before_credentials(make_skill, tmp_path, forbid_credentials):
    for i in range(150):
        make_skill(f'large-{i:03}', description='Very detailed skill. ' * 20)
    router = Router(Config(roots=[str(tmp_path / 'skills')], max_request_bytes=8000, max_api_calls=2))
    plan = router.plan('Perform work')
    assert not plan['ready'] and 'call budget' in plan['reason']
    assert plan['base_requests_upper_bound'] > plan['http_request_limit']
    assert plan['http_requests'] == 0
    with pytest.raises(RouterError, match='call budget'):
        router.route('Perform work')
    assert router.client is None and not router.cache


def test_oversized_evidence_reports_local_block(make_skill, tmp_path, forbid_credentials):
    make_skill(body='😀' * 3000)
    router = Router(Config(roots=[str(tmp_path / 'skills')], excerpt_chars=2000, max_request_bytes=8000))
    plan = router.plan('Debug Python')
    assert not plan['ready'] and 'request budget' in plan['reason']
    assert plan['http_requests'] == 0 and router.client is None


def test_plan_shards_and_retry_bound(make_skill, tmp_path):
    for i in range(140):
        make_skill(f'unit-{i:03}', description='Inspect specialized operation inputs and outputs.')
    cfg = Config(roots=[str(tmp_path / 'skills')], max_request_bytes=8000, retries=1)
    provider = RecordedProvider()
    router = Router(cfg, JevClient(cfg, 'fixture-key', httpx.MockTransport(provider)))
    try:
        plan = router.plan('Inspect operation')
        assert plan['ready'] and plan['rank_requests'] > 1
        assert not provider.requests
        result = router.route('Inspect operation')
        assert result['api_calls'] <= plan['base_requests_upper_bound']
        assert plan['http_requests_upper_bound'] == min(cfg.max_api_calls, 2 * plan['base_requests_upper_bound'])
    finally:
        router.close()


def test_offline_and_empty_plans(skill_root, tmp_path, forbid_credentials):
    offline = Router(Config(roots=[str(skill_root)], mode='offline'))
    plan = offline.plan('Debug Python')
    assert plan['ready'] and plan['base_requests_upper_bound'] == 0
    empty = Router(Config(roots=[str(tmp_path / 'missing')]))
    plan = empty.plan('Debug Python')
    assert not plan['ready'] and plan['warnings'] and plan['http_requests'] == 0


@pytest.mark.parametrize('task,context', [('', ''), ('valid', None), ('가' * 2100, ''), ('\ud800', '')])
def test_route_and_plan_share_input_validation(skill_root, task, context, forbid_credentials):
    router = Router(Config(roots=[str(skill_root)]))
    for method in (router.plan, router.route):
        with pytest.raises(RouterError):
            method(task, context)
    assert router.client is None


def test_cli_plan_exit_status_and_no_task_echo(skill_root, tmp_path, capsys, forbid_credentials):
    path = tmp_path / 'config.json'
    Config(roots=[str(skill_root)]).save(path)
    assert main(['--config', str(path), 'plan', 'Private focused task', '--context', 'Private context']) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result['http_requests'] == 0 and result['credentials_checked'] is False
    assert 'Private' not in captured.out and captured.err == ''
    Config(roots=[]).save(path)
    assert main(['--config', str(path), 'plan', 'Task']) == 1
    assert json.loads(capsys.readouterr().out)['ready'] is False


def test_cli_read_continuation_binds_file_revision(make_skill, tmp_path, capsys):
    directory = make_skill(body='original ' * 400)
    path = tmp_path / 'config.json'
    cfg = Config(roots=[str(directory.parent)], mode='offline', max_output_chars=1000)
    cfg.save(path)
    sid = next(iter(Router(cfg).catalog.skills))
    base = ['--config', str(path), 'read', sid]
    assert main(base) == 0
    first = json.loads(capsys.readouterr().out)
    more = base + ['--offset', str(first['next_offset'])]
    assert main(more) == 2
    assert 'expected-digest' in capsys.readouterr().err
    more += ['--expected-digest', first['content_digest']]
    assert main(more) == 0
    assert json.loads(capsys.readouterr().out)['content_digest'] == first['content_digest']
    source = directory / 'SKILL.md'
    source.write_text(source.read_text(encoding='utf-8').replace('original', 'modified'), encoding='utf-8')
    assert main(more) == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'changed' in captured.err and 'Traceback' not in captured.err


def test_setup_honors_configured_catalog_limit(make_skill, tmp_path, capsys):
    first = make_skill(root=tmp_path / 'one')
    second = make_skill('second', root=tmp_path / 'two')
    path = tmp_path / 'config.json'
    Config(roots=[str(first.parent)], max_catalog_skills=1).save(path)
    before = path.read_bytes()
    assert main(['--config', str(path), 'setup', '--root', str(second.parent)]) == 2
    assert 'max_catalog_skills' in capsys.readouterr().err
    assert path.read_bytes() == before
