import json
import httpx
import pytest
from jev_skill_router.config import Config,RouterError
from jev_skill_router.jev import JevClient,validate_response

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
