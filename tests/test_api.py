import json
import asyncio
import time
import httpx
import pytest
from jev_skill_router.config import Config,RouterError
from jev_skill_router.jev import JevClient,RequestBudget,validate_response

Q={'check':{'type':'noul','instructions':'Is the task supported?'}}
VALID={'model':'fixture','answers':{'check':{'type':'noul','noul':.8}},'usage':{'input_tokens':10,'output_tokens':2}}

def test_documented_endpoint_body_headers():
    def handle(request):
        assert str(request.url)=='https://api.typesafe.ai/v1/systemone'
        assert request.headers['authorization']=='Bearer fixture-key'
        assert json.loads(request.content)=={'model':'jev-latest','state':{'task':'한국어'},'questions':Q}
        return httpx.Response(200,json=VALID)
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle))
    try:assert client.ask({'task':'한국어'},Q)['answers']['check']['noul']==.8
    finally:client.close()

@pytest.mark.parametrize('status',[429,529,503])
def test_retry_with_backoff(status):
    calls=[];sleeps=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(status,headers={'Retry-After':'2'}) if len(calls)==1 else httpx.Response(200,json=VALID)
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle),sleep=sleeps.append)
    try:client.ask({},Q)
    finally:client.close()
    assert len(calls)==2 and sleeps==[2.0]

def test_long_retry_after_not_ignored():
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':'100'})))
    try:
        with pytest.raises(RouterError,match='longer retry'):client.ask({},Q)
    finally:client.close()

@pytest.mark.parametrize('status',[401,422,302])
def test_no_retry_or_secret_error_leak(status):
    calls=[]
    def handle(request):calls.append(1);return httpx.Response(status,json={'secret':'do-not-echo'})
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle))
    try:
        with pytest.raises(RouterError) as e:client.ask({},Q)
        assert 'do-not-echo' not in str(e.value) and len(calls)==1
    finally:client.close()

def test_network_failure_is_not_retried():
    calls=[]
    def handle(request):calls.append(1);raise httpx.ConnectTimeout('private upstream text')
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle))
    try:
        with pytest.raises(RouterError,match='timed out'):client.ask({},Q)
        assert len(calls)==1
    finally:client.close()

@pytest.mark.parametrize('value',[True,1.1,-.1,float('nan'),float('inf'),'0.9'])
def test_invalid_noul_rejected(value):
    with pytest.raises(RouterError):validate_response({'model':'fixture','answers':{'check':{'type':'noul','noul':value}}},Q)

def test_choice_requires_known_ids_and_correct_winner():
    q={'rank':{'type':'choice','criteria':{'a':'A','b':'B'}}}
    answer={'model':'fixture','answers':{'rank':{'type':'choice','choice':'a','probabilities':{'a':.1,'b':.9},'confidence':.8}}}
    with pytest.raises(RouterError):validate_response(answer,q)
    answer['answers']['rank']['choice']='b'
    assert validate_response(answer,q)==answer
    answer['answers']['rank']['probabilities']={'c':1}
    with pytest.raises(RouterError):validate_response(answer,q)

def test_request_budget_checked_before_http():
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(lambda r:pytest.fail('Network called')))
    try:
        with pytest.raises(RouterError,match='byte budget'):client.ask({'task':'가'*9000},Q)
    finally:client.close()

def test_protocol_network_error_is_sanitized():
    def handle(request):raise httpx.RemoteProtocolError('sensitive upstream detail')
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle))
    try:
        with pytest.raises(RouterError) as e:client.ask({},Q)
        assert 'sensitive' not in str(e.value)
    finally:client.close()

def test_concurrency_is_bounded_and_answers_keep_input_order():
    active=0;peak=0
    async def handle(request):
        nonlocal active,peak
        number=int(json.loads(request.content)['questions']['check']['instructions'])
        active+=1;peak=max(peak,active)
        try:await asyncio.sleep(.003*(6-number))
        finally:active-=1
        return httpx.Response(200,json={**VALID,'model':str(number)})
    client=JevClient(Config(max_concurrency=2),'fixture-key',httpx.MockTransport(handle))
    questions=[{'check':{'type':'noul','instructions':str(i)}} for i in range(6)]
    try:
        results=client.ask_many({},questions,budget=RequestBudget(10,time.monotonic()+2))
        assert [r['model'] for r in results]==[str(i) for i in range(6)]
        assert peak==2 and active==0
        assert client.metrics_snapshot()['http_requests']==6
    finally:client.close()

def test_deadline_cancels_inflight_and_queued_requests():
    started=0;active=0
    async def handle(request):
        nonlocal started,active
        started+=1;active+=1
        try:await asyncio.sleep(10)
        finally:active-=1
        return httpx.Response(200,json=VALID)
    client=JevClient(Config(max_concurrency=2),'fixture-key',httpx.MockTransport(handle))
    try:
        with pytest.raises(RouterError,match='deadline'):
            client.ask_many({},[Q]*10,budget=RequestBudget(10,time.monotonic()+.03))
        assert started==2 and active==0
        assert client.metrics_snapshot()['unreported_requests']==2
    finally:client.close()

def test_failure_cancels_other_requests_and_never_starts_queue():
    started=[];active=0
    async def handle(request):
        nonlocal active
        number=int(json.loads(request.content)['questions']['check']['instructions'])
        started.append(number);active+=1
        try:
            await asyncio.sleep(.01 if number==0 else 10)
            return httpx.Response(401,json={'private':'do not echo'})
        finally:active-=1
    client=JevClient(Config(max_concurrency=2),'fixture-key',httpx.MockTransport(handle))
    questions=[{'check':{'type':'noul','instructions':str(i)}} for i in range(10)]
    try:
        with pytest.raises(RouterError,match='HTTP 401'):
            client.ask_many({},questions,budget=RequestBudget(10,time.monotonic()+2))
        assert active==0
        assert started==[0,1]
    finally:client.close()

def test_retries_count_toward_physical_and_lifetime_budgets():
    calls=[]
    def handle(request):
        calls.append(1)
        return httpx.Response(503) if len(calls)==1 else httpx.Response(200,json=VALID)
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle),sleep=lambda _:None,max_requests=2)
    try:
        client.ask({},Q)
        metrics=client.metrics_snapshot()
        assert metrics['http_requests']==2 and metrics['retry_requests']==1
        assert metrics['input_tokens']==10 and metrics['unreported_requests']==1
        with pytest.raises(RouterError,match='Evaluation HTTP request budget'):
            client.ask({},Q)
        assert len(calls)==2
    finally:client.close()

def test_shared_route_budget_includes_retries():
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(lambda _:httpx.Response(503)),sleep=lambda _:None)
    try:
        with pytest.raises(RouterError,match='HTTP request budget'):
            client.ask({},Q,budget=RequestBudget(1,time.monotonic()+10))
        assert client.metrics_snapshot()['http_requests']==1
    finally:client.close()

def test_retry_delay_does_not_outlive_route_deadline():
    sleeps=[]
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(lambda _:httpx.Response(429,headers={'retry-after':'2'})),sleep=sleeps.append)
    try:
        with pytest.raises(RouterError,match='remaining routing deadline'):
            client.ask({},Q,budget=RequestBudget(5,time.monotonic()+.1))
        assert sleeps==[] and client.metrics_snapshot()['http_requests']==1
    finally:client.close()
