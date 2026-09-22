from __future__ import annotations
import json
from pathlib import Path
import httpx
import pytest
from jev_skill_router.config import Config
from jev_skill_router.jev import JevClient

@pytest.fixture
def make_skill(tmp_path):
    def make(name='python-debug', description='Debug Python tracebacks and failing tests.', body='Inspect the exception and run the regression test.', root=None):
        directory=(root or tmp_path/'skills')/name
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'SKILL.md').write_text('---\nname: '+name+'\ndescription: '+description+'\n---\n\n'+body,encoding='utf-8')
        return directory
    return make

@pytest.fixture
def skill_root(make_skill):
    return make_skill().parent

class RecordedProvider:
    """Deterministic HTTP fixture, never a model-quality simulation."""
    def __init__(self, fit=.91, confidence=.9):
        self.fit=fit;self.confidence=confidence;self.requests=[]
    def __call__(self,request):
        body=json.loads(request.content);self.requests.append(body)
        answers={}
        for key,q in body['questions'].items():
            if q['type']=='choice':
                options=list(q['criteria'])
                chosen=next(k for k in options if k!='__none__')
                answers[key]={'type':'choice','choice':chosen,'probabilities':{k:float(k==chosen) for k in options},'confidence':.9}
            elif q['type']=='noul':answers[key]={'type':'noul','noul':self.fit}
            else:answers[key]={'type':'score','score':1.9,'probabilities':{'0':0,'1':.1,'2':.9},'legend':dict(enumerate(q['criteria'])),'confidence':self.confidence}
        return httpx.Response(200,json={'model':'fixture-not-live','answers':answers,'usage':{'input_tokens':100,'output_tokens':10}})

@pytest.fixture
def provider():return RecordedProvider()

@pytest.fixture
def live_router(skill_root,provider):
    from jev_skill_router.router import Router
    cfg=Config(roots=[str(skill_root)])
    client=JevClient(cfg,'fixture-key',transport=httpx.MockTransport(provider),sleep=lambda _:None)
    router=Router(cfg,client)
    yield router
    router.close()
