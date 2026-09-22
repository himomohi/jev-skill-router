import json
import asyncio
import httpx
import pytest
from jev_skill_router.config import Config,RouterError
from jev_skill_router.router import Router
from jev_skill_router.jev import JevClient,encoded
from conftest import RecordedProvider

def test_two_stage_flow_and_usage(live_router,provider):
    result=live_router.route('Debug Python tracebacks')
    assert result['status']=='selected' and result['api_calls']==2
    assert result['provider']=='jev' and result['models']==['fixture-not-live']
    assert result['usage']=={'input_tokens':200,'output_tokens':20}
    assert 'Inspect the exception' in result['selected'][0]['content']
    assert 'rank' in provider.requests[0]['questions']
    questions=provider.requests[1]['questions']
    assert questions['fit_0']['instructions']['skill']==questions['quality_0']['instructions']['skill']

def test_low_fit_no_match(live_router,provider):
    provider.fit=.2
    result=live_router.route('Do an unrelated thing')
    assert result['status']=='no_match' and not result['selected']

def test_low_confidence_does_not_inject(live_router,provider):
    provider.confidence=.1
    result=live_router.route('Debug Python')
    assert result['status']=='uncertain' and result['selected']==[]

def test_exact_repeat_cached_and_edit_invalidates(live_router,provider):
    live_router.route('Debug Python')
    result=live_router.route('Debug Python')
    assert result['cache_hit'] and result['api_calls']==0 and len(provider.requests)==2
    source=next(iter(live_router.catalog.skills.values())).source
    source.write_text(source.read_text()+'\nA new requirement.')
    result=live_router.route('Debug Python')
    assert not result['cache_hit'] and len(provider.requests)==4
    assert 'new requirement' in result['selected'][0]['content']

def test_offline_is_explicitly_labeled(skill_root):
    router=Router(Config(roots=[str(skill_root)],mode='offline'))
    result=router.route('Debug Python')
    assert result['provider']=='offline-lexical-demo' and result['api_calls']==0
    assert result['selected'][0]['confidence'] is None

def test_no_silent_fallback_without_key(skill_root,monkeypatch):
    def missing():raise RouterError('No key fixture')
    monkeypatch.setattr('jev_skill_router.router.api_key',missing)
    router=Router(Config(roots=[str(skill_root)]))
    with pytest.raises(RouterError,match='No key'):router.route('Debug Python')

def test_many_skills_sharded_without_unknown_choices(make_skill,tmp_path):
    for i in range(270):make_skill(f'unit-{i:03d}',description='Specialized operation with bounded inputs and expected outputs.')
    provider=RecordedProvider();cfg=Config(roots=[str(tmp_path/'skills')],max_request_bytes=8000)
    client=JevClient(cfg,'fixture-key',httpx.MockTransport(provider));router=Router(cfg,client)
    try:result=router.route('Find an operation')
    finally:router.close()
    assert result['catalog_size']==270 and result['api_calls']>2
    assert all(len(encoded(r))<=8000 for r in provider.requests)
    choices=[r['questions']['rank']['criteria'] for r in provider.requests if 'rank' in r['questions']]
    assert all(len(c)<=129 for c in choices)
    assert sum(len(c)-1 for c in choices)==270

def test_preflight_budget_before_paid_requests(make_skill,tmp_path):
    for i in range(150):make_skill(f'skill-{i:03}',description='Very detailed skill. '*20)
    provider=RecordedProvider();cfg=Config(roots=[str(tmp_path/'skills')],max_request_bytes=8000,max_api_calls=2)
    client=JevClient(cfg,'fixture-key',httpx.MockTransport(provider));router=Router(cfg,client)
    try:
        with pytest.raises(RouterError,match='call budget'):router.route('Perform work')
        assert provider.requests==[]
    finally:router.close()

def test_request_limits_utf8(live_router,provider):
    with pytest.raises(RouterError,match='6000-byte'):live_router.route('가'*2100)
    assert not provider.requests

def test_multiple_skills_and_output_budget(make_skill,tmp_path):
    for i in range(3):make_skill(f'debug-{i}',body='long instructions '*2000)
    provider=RecordedProvider();cfg=Config(roots=[str(tmp_path/'skills')],max_skills=3,max_output_chars=1200)
    router=Router(cfg,JevClient(cfg,'fixture-key',httpx.MockTransport(provider)))
    try:result=router.route('Debug Python')
    finally:router.close()
    assert len(result['selected'])==3
    assert sum(len(s['content']) for s in result['selected'])<=1200
    assert all(s['next_offset'] is not None for s in result['selected'])

def test_choice_criteria_use_documented_plain_descriptions(live_router,provider):
    live_router.route('Debug Python')
    criteria=provider.requests[0]['questions']['rank']['criteria']
    assert all(isinstance(value,str) for value in criteria.values())
    assert any('python-debug: Debug Python' in value for value in criteria.values())

def test_long_body_evidence_includes_relevant_late_capability_and_tail(make_skill,tmp_path):
    from jev_skill_router.evidence import excerpt
    body='Introduction\n'+('general overview. '*300)+'\nSupports forensic_analysis of parquet files.\n'+('miscellaneous notes. '*100)+'\nFinal constraint: read-only.'
    selected=excerpt(body,'forensic_analysis parquet',900)
    assert len(selected)<=900
    assert 'Introduction' in selected and 'parquet' in selected
    assert 'Final constraint: read-only.' in selected
    assert 'parquet' not in body[:900]
    make_skill(body=body)
    router=Router(Config(roots=[str(tmp_path/'skills')],mode='offline'))
    skill=next(iter(router.catalog.skills.values()))
    question=router.verify_questions([skill],'forensic_analysis parquet')['fit_0']['instructions']['skill']
    assert question['excerpt_truncated'] and 'parquet' in question['instructions_excerpt']

def test_excerpt_keeps_short_body_and_samples_without_language_overlap():
    from jev_skill_router.evidence import excerpt
    assert excerpt('A complete short skill.','한국어 요청',100)=='A complete short skill.'
    body='HEAD'+('a'*996)+'MIDDLE'+('b'*990)+'TAIL'
    sample=excerpt(body,'관련 기능을 찾아줘',200)
    assert len(sample)<=200 and 'HEAD' in sample and 'TAIL' in sample
    assert 'a' in sample and 'b' in sample

def test_cached_latency_is_current_and_catalog_reloads_are_reported(skill_root,provider):
    async def handle(request):
        await asyncio.sleep(.015)
        return provider(request)
    cfg=Config(roots=[str(skill_root)])
    router=Router(cfg,JevClient(cfg,'fixture-key',httpx.MockTransport(handle)))
    try:
        cold=router.route('Debug Python')
        warm=router.route('Debug Python')
        assert cold['http_requests']==2 and warm['http_requests']==0
        assert warm['elapsed_seconds']<cold['elapsed_seconds']
        assert warm['routing_seconds']<warm['original_routing_seconds']
        assert router.last_metrics['http_requests']==0
        from jev_skill_router.catalog import STAT_CACHE_SUPPORTED
        if STAT_CACHE_SUPPORTED:
            assert router.last_metrics['catalog_refresh']['files_reloaded']==0
    finally:router.close()

def test_error_preserves_actual_request_counts_and_never_caches(skill_root):
    cfg=Config(roots=[str(skill_root)],retries=0)
    router=Router(cfg,JevClient(cfg,'fixture-key',httpx.MockTransport(lambda _:httpx.Response(401))))
    try:
        with pytest.raises(RouterError,match='HTTP 401'):router.route('Debug Python')
        assert router.last_metrics['http_requests']==1
        assert router.last_metrics['unreported_requests']==1
        assert not router.cache
    finally:router.close()
