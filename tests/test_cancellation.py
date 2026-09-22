"""Host cancellation and transport lifecycle regressions; no paid HTTP calls."""
import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from jev_skill_router.config import Config
from jev_skill_router.jev import CancellationToken, JevClient, RequestBudget, RoutingCancelled
from jev_skill_router.mcp import MAX_PENDING_CALLS, ProtocolError, Server, _ToolWorker
from jev_skill_router.router import Router

ROOT=Path(__file__).resolve().parents[1]
Q={'check':{'type':'noul','instructions':'Is this supported?'}}
VALID={'model':'fixture','answers':{'check':{'type':'noul','noul':.8}}}


def request(method,params=None,id=1):
    return {'jsonrpc':'2.0','id':id,'method':method,'params':params or {}}


def call(task,id):
    return request('tools/call',{'name':'skill_router','arguments':{'action':'route','task':task}},id)


def test_precancelled_request_never_starts_http():
    token=CancellationToken();token.cancel()
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(lambda _:pytest.fail('HTTP started')))
    budget=RequestBudget(10,time.monotonic()+10,cancellation=token)
    try:
        with pytest.raises(RoutingCancelled,match='Routing cancelled'):
            client.ask({},Q,budget=budget)
        assert budget.used==0 and client.metrics_snapshot()['http_requests']==0
    finally:client.close()


def test_cancellation_stops_inflight_and_queued_http_and_client_can_be_reused():
    token=CancellationToken();started=threading.Event();calls=[];active=0
    async def handle(request):
        nonlocal active
        calls.append(1);active+=1
        try:
            if len(calls)<=2:
                if len(calls)==2:started.set()
                await asyncio.sleep(30)
            return httpx.Response(200,json=VALID)
        finally:active-=1
    client=JevClient(Config(max_concurrency=2),'fixture-key',httpx.MockTransport(handle))
    def cancel():
        if started.wait(5):token.cancel()
    thread=threading.Thread(target=cancel);thread.start()
    try:
        with pytest.raises(RoutingCancelled):
            client.ask_many({},[Q]*20,budget=RequestBudget(30,time.monotonic()+10,cancellation=token))
        assert len(calls)==2 and active==0
        assert client.ask({},Q)['model']=='fixture'
        assert len(calls)==3 and active==0
    finally:
        token.cancel();thread.join(5);client.close()


def test_cancellation_during_retry_wait_never_sends_retry():
    token=CancellationToken();waiting=threading.Event();calls=[]
    def handle(request):
        calls.append(1)
        return httpx.Response(503)
    async def pause(delay):
        waiting.set()
        await asyncio.sleep(30)
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(handle),sleep=pause)
    def cancel():
        if waiting.wait(5):token.cancel()
    thread=threading.Thread(target=cancel);thread.start()
    try:
        with pytest.raises(RoutingCancelled):
            client.ask({},Q,budget=RequestBudget(10,time.monotonic()+10,cancellation=token))
        assert len(calls)==1 and client.metrics_snapshot()['retry_requests']==0
    finally:
        token.cancel();thread.join(5);client.close()


def test_cancellation_mid_response_closes_stream_without_retry():
    token=CancellationToken();reading=threading.Event();closed=threading.Event()
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"model":'
            reading.set()
            await asyncio.sleep(30)
        async def aclose(self):closed.set()
    client=JevClient(Config(),'fixture-key',httpx.MockTransport(
        lambda _:httpx.Response(200,stream=SlowBody())))
    def cancel():
        if reading.wait(5):token.cancel()
    thread=threading.Thread(target=cancel);thread.start()
    try:
        with pytest.raises(RoutingCancelled):
            client.ask({},Q,budget=RequestBudget(10,time.monotonic()+10,cancellation=token))
        assert closed.is_set() and client.metrics_snapshot()['http_requests']==1
        assert client.metrics_snapshot()['retry_requests']==0
    finally:
        token.cancel();thread.join(5);client.close()


def test_precancelled_route_never_refreshes_catalog_or_caches(skill_root,monkeypatch):
    router=Router(Config(roots=[str(skill_root)],mode='offline'))
    token=CancellationToken();token.cancel()
    monkeypatch.setattr(router.catalog,'refresh',lambda:pytest.fail('Cancelled route refreshed catalog'))
    try:
        with pytest.raises(RoutingCancelled):router.route('Debug Python',cancellation=token)
        assert router.cache=={} and router.last_metrics['http_requests']==0
    finally:router.close()


def test_worker_serializes_fifo_bounds_queue_and_closes_on_its_owner_thread():
    started=threading.Event();release=threading.Event();done=threading.Event()
    class TestRouter:
        def __init__(self):self.tasks=[];self.owner=None;self.closed=None
        def route(self,task,context='',*,cancellation=None):
            assert self.owner in (None,threading.get_ident())
            self.owner=threading.get_ident();self.tasks.append(task)
            if task=='blocked':started.set();assert release.wait(5)
            cancellation.check()
            return {'task':task}
        def close(self):self.closed=threading.get_ident()
    router=TestRouter();server=Server(router);server.initialized=True;responses=[]
    def emit(response):
        responses.append(response)
        if response['id']==100:done.set()
        return True
    worker=_ToolWorker(server,emit)
    try:
        worker.submit(call('blocked',1));assert started.wait(5)
        for i in range(2,MAX_PENDING_CALLS+1):worker.submit(call(str(i),i))
        with pytest.raises(ProtocolError) as full:worker.submit(call('overflow',99))
        assert full.value.code==-32000
        with pytest.raises(ProtocolError) as duplicate:worker.submit(call('duplicate',1))
        assert duplicate.value.code==-32600
        worker.cancel({'requestId':2})
        worker.submit(call('last',100))
        worker.cancel({'requestId':1,'reason':'private text is never echoed'})
        release.set();assert done.wait(5)
        assert [r['id'] for r in responses]==list(range(3,MAX_PENDING_CALLS+1))+[100]
        assert router.tasks==['blocked']+[str(i) for i in range(3,MAX_PENDING_CALLS+1)]+['last']
    finally:
        release.set();worker.close()
    assert router.closed==router.owner and router.closed!=threading.get_ident()


CHILD_SCRIPT=r'''
import asyncio,json,sys,threading
import httpx
from jev_skill_router.config import Config
from jev_skill_router.jev import JevClient
from jev_skill_router.mcp import serve
from jev_skill_router.router import Router

async def handle(request):
    payload=json.loads(request.content)
    task=payload['state']['task']
    print('start:'+task+':'+str(threading.get_ident()),file=sys.stderr,flush=True)
    if task=='block':
        try:await asyncio.sleep(30)
        finally:print('stopped:block',file=sys.stderr,flush=True)
    answers={}
    for key,q in payload['questions'].items():
        if q['type']=='choice':
            selected=next(k for k in q['criteria'] if k!='__none__')
            answers[key]={'type':'choice','choice':selected,'confidence':.9,
                          'probabilities':{k:float(k==selected) for k in q['criteria']}}
        elif q['type']=='noul':answers[key]={'type':'noul','noul':.9}
        else:answers[key]={'type':'score','score':2,'confidence':.9,
                          'probabilities':{'0':0,'1':0,'2':1}}
    return httpx.Response(200,json={'model':'fixture-not-live','answers':answers})

class CheckedRouter(Router):
    def close(self):
        super().close()
        print('closed:'+str(threading.get_ident()),file=sys.stderr,flush=True)

cfg=Config(roots=[sys.argv[1]])
client=JevClient(cfg,'fixture-key',httpx.MockTransport(handle))
raise SystemExit(serve(CheckedRouter(cfg,client)))
'''


class Child:
    def __init__(self,skill_root):
        self.process=subprocess.Popen([sys.executable,'-c',CHILD_SCRIPT,str(skill_root)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
        self.responses=queue.Queue();self.events=queue.Queue()
        def read(stream,target):
            for line in stream:target.put(line.strip())
        self.readers=[threading.Thread(target=read,args=(self.process.stdout,self.responses),daemon=True),
                      threading.Thread(target=read,args=(self.process.stderr,self.events),daemon=True)]
        for thread in self.readers:thread.start()
    def send(self,message):
        self.process.stdin.write(json.dumps(message)+'\n');self.process.stdin.flush()
    def receive(self):return json.loads(self.responses.get(timeout=5))
    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.wait();raise
        finally:
            for thread in self.readers:thread.join(5)
            self.process.stdout.close();self.process.stderr.close()


def test_stdio_cancel_remains_responsive_and_followup_works(skill_root):
    child=Child(skill_root)
    try:
        child.send(request('initialize',{'protocolVersion':'2025-06-18'}));assert child.receive()['id']==1
        child.send(call('block',2));event=child.events.get(timeout=5);assert event.startswith('start:block:')
        child.send(call('queued-never-started',3))
        for params in ({'requestId':999},{'requestId':[]},{'requestId':2,'reason':[]},[]):
            child.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':params})
        child.send(request('ping',id=4));assert child.receive()=={'jsonrpc':'2.0','id':4,'result':{}}
        child.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':3}})
        child.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':2}})
        assert child.events.get(timeout=5)=='stopped:block'
        child.send(call('next',5));response=child.receive()
        assert response['id']==5 and not response['result']['isError']
        result=json.loads(response['result']['content'][0]['text'])
        assert result['selected'][0]['name']=='python-debug'
    finally:child.close()
    assert child.process.returncode==0 and child.responses.empty()
    events=[]
    while not child.events.empty():events.append(child.events.get_nowait())
    assert events[-1]=='closed:'+event.rsplit(':',1)[1]
    assert not any('queued-never-started' in entry or 'Traceback' in entry for entry in events)


def test_stdio_eof_cancels_active_and_queued_work_and_closes_pool(skill_root):
    child=Child(skill_root)
    try:
        child.send(request('initialize',{'protocolVersion':'2025-06-18'}));child.receive()
        child.send(call('block',2));event=child.events.get(timeout=5);assert event.startswith('start:block:')
        child.send(call('queued-never-started',3))
    finally:child.close()
    assert child.process.returncode==0 and child.responses.empty()
    assert child.events.get_nowait()=='stopped:block'
    assert child.events.get_nowait()=='closed:'+event.rsplit(':',1)[1]
    assert child.events.empty()
