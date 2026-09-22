import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import pytest
from jev_skill_router.config import Config,RouterError
from jev_skill_router.router import Router
from jev_skill_router.mcp import Server,dispatch
from jev_skill_router.migration import park,restore
from jev_skill_router.integrations import install_client,merge_json

ROOT=Path(__file__).resolve().parents[1]

def request(method,params=None,id=1):return {'jsonrpc':'2.0','id':id,'method':method,'params':params or {}}

def test_protocol_single_static_tool(skill_root):
    server=Server(Router(Config(roots=[str(skill_root)],mode='offline')))
    assert server.handle(request('tools/list'))['error']['code']==-32002
    assert server.handle(request('initialize',{'protocolVersion':'2025-06-18'}))['result']['protocolVersion']=='2025-06-18'
    tools=server.handle(request('tools/list'))['result']['tools']
    assert len(tools)==1 and tools[0]['name']=='skill_router'
    assert 'python-debug' not in json.dumps(tools)
    response=server.handle(request('tools/call',{'name':'skill_router','arguments':{'action':'read','skill_id':'bad'}}))
    assert response['result']['isError']

def test_real_subprocess_stdio(skill_root,tmp_path):
    config=tmp_path/'config.json';Config(roots=[str(skill_root)],mode='offline').save(config)
    messages=[request('initialize',{'protocolVersion':'2025-06-18'}),{'jsonrpc':'2.0','method':'notifications/initialized'},request('tools/list',id=2),request('tools/call',{'name':'skill_router','arguments':{'action':'route','task':'Debug Python'}},id=3)]
    env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
    process=subprocess.Popen([sys.executable,'-m','jev_skill_router','--config',str(config),'serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    received=queue.Queue()
    def read_responses():
        for line in process.stdout:received.put(json.loads(line))
    reader=threading.Thread(target=read_responses,daemon=True);reader.start()
    try:
        process.stdin.write('\n'.join(json.dumps(m) for m in messages)+'\n');process.stdin.flush()
        # EOF means the client disconnected and cancels unfinished calls. Wait
        # for the tool result while the actual stdio session is still open.
        responses=[received.get(timeout=15) for _ in range(3)]
        process.stdin.close();process.wait(timeout=15)
        assert process.returncode==0 and process.stderr.read()==''
    finally:
        if process.poll() is None:process.kill();process.wait()
        reader.join(5)
        for stream in (process.stdin,process.stdout,process.stderr):stream.close()
    assert [r['id'] for r in responses]==[1,2,3]
    content=json.loads(responses[-1]['result']['content'][0]['text'])
    assert content['selected'][0]['name']=='python-debug'


def test_stdio_rejects_malformed_frames_and_keeps_session_alive(tmp_path):
    config=tmp_path/'config.json';Config(mode='offline').save(config)
    frames=[
        b'['*10000+b'0'+b']'*10000,
        json.dumps(request('ping',id='\ud800')).encode(),
        json.dumps(request('ping',{'invalid':'\ud800'})).encode(),
        b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"value":NaN}}',
        b'\xff',
    ]
    frames.append(json.dumps(request('ping',id='한국어-🐱'),ensure_ascii=False).encode())
    process=subprocess.run([sys.executable,'-m','jev_skill_router','--config',str(config),'serve'],input=b'\n'.join(frames)+b'\n',capture_output=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},timeout=15)
    assert process.returncode==0 and process.stderr==b''
    responses=[json.loads(line) for line in process.stdout.splitlines()]
    assert len(responses)==len(frames)
    assert all(response['error']['code']==-32700 for response in responses[:-1])
    assert responses[-1]=={'jsonrpc':'2.0','id':'한국어-🐱','result':{}}


def test_invalid_unicode_request_id_has_safe_error():
    server=Server(None)
    result=server.handle(request('ping',id='\ud800'))
    assert result['id'] is None and result['error']['code']==-32600


def test_mcp_continuation_requires_matching_file_digest(make_skill):
    skill=make_skill(body='Read these instructions. '*120)
    router=Router(Config(roots=[str(skill.parent)],mode='offline',max_output_chars=1000))
    try:
        sid=next(iter(router.catalog.skills))
        args={'action':'read','skill_id':sid}
        first=dispatch(router,args)
        continued={**args,'offset':first['next_offset']}
        with pytest.raises(RouterError,match='expected_digest'):
            dispatch(router,continued)
        continued['expected_digest']=first['content_digest']
        second=dispatch(router,continued)
        assert second['offset']==first['next_offset'] and second['content_digest']==first['content_digest']
        file=skill/'SKILL.md';file.write_text(file.read_text()+'\nChanged instruction.',encoding='utf-8')
        with pytest.raises(RouterError,match='changed'):
            dispatch(router,continued)
    finally:router.close()


@pytest.mark.parametrize('field,value',[('offset',True),('offset','1'),('offset',-1),('expected_digest',None),('expected_digest',123),('expected_digest','A'*64),('expected_digest','bad')])
def test_mcp_invalid_continuation_arguments_are_tool_errors(skill_root,field,value):
    router=Router(Config(roots=[str(skill_root)],mode='offline'))
    try:
        server=Server(router);server.handle(request('initialize',{'protocolVersion':'2025-06-18'}))
        result=server.handle(request('tools/call',{'name':'skill_router','arguments':{'action':'read','skill_id':next(iter(router.catalog.skills)),field:value}}))
        assert result['result']['isError']
    finally:router.close()

def test_hook_protocol(skill_root,tmp_path):
    config=tmp_path/'config.json';Config(roots=[str(skill_root)],mode='offline').save(config)
    process=subprocess.run([sys.executable,'-m','jev_skill_router','--config',str(config),'hook'],input=json.dumps({'prompt':'Debug Python'}),capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},timeout=15)
    assert process.returncode==0
    payload=json.loads(process.stdout)['hookSpecificOutput']
    assert payload['hookEventName']=='UserPromptSubmit' and 'python-debug' in payload['additionalContext']

def test_migration_dry_run_and_restore(make_skill,tmp_path):
    skill=make_skill();root=skill.parent;config_file=tmp_path/'config.json'
    cfg=Config(roots=[str(root)],mode='offline');cfg.save(config_file)
    preview=park(root,cfg,config_file,vault=tmp_path/'vault')
    assert preview['dry_run'] and skill.exists() and not (tmp_path/'vault').exists()
    result=park(root,cfg,config_file,True,tmp_path/'vault')
    assert not skill.exists()
    assert len(Router(Config.load(config_file)).catalog.skills)==1
    manifest=Path(result['manifest']);assert restore(manifest)['dry_run']
    cfg=Config.load(config_file);cfg.roots.append(str(tmp_path/'other'));cfg.save(config_file)
    restore(manifest,True)
    assert skill.exists() and str(tmp_path/'other') in Config.load(config_file).roots
    assert str(root) in Config.load(config_file).roots

def test_restore_unregistered_original_root(make_skill,tmp_path):
    skill=make_skill();cfg=Config(mode='offline');file=tmp_path/'config.json';cfg.save(file)
    result=park(skill.parent,cfg,file,True,tmp_path/'vault')
    restore(Path(result['manifest']),True)
    assert str(skill.parent) in Config.load(file).roots

def test_restore_conflict_never_overwrites(make_skill,tmp_path):
    skill=make_skill();cfg=Config(roots=[str(skill.parent)]);file=tmp_path/'config.json';cfg.save(file)
    result=park(skill.parent,cfg,file,True,tmp_path/'vault')
    skill.mkdir();(skill/'important.txt').write_text('keep')
    with pytest.raises(RouterError,match='overwrite'):restore(Path(result['manifest']),True)
    assert (skill/'important.txt').read_text()=='keep'

def test_park_preserves_bridge_and_system(make_skill,tmp_path):
    skill=make_skill();make_skill('jev-skill-router');make_skill('builtin',root=skill.parent/'.system')
    cfg=Config(roots=[str(skill.parent)]);file=tmp_path/'config.json';cfg.save(file)
    result=park(skill.parent,cfg,file,True,tmp_path/'vault')
    assert len(result['operations'])==1
    assert (skill.parent/'jev-skill-router').exists() and (skill.parent/'.system').exists()

def test_cursor_preserves_other_servers_and_backup(tmp_path):
    target=tmp_path/'.cursor/mcp.json';target.parent.mkdir();target.write_text('{"mcpServers":{"other":{"command":"other"}},"custom":true}')
    result=install_client('cursor',tmp_path/'config.json',home=tmp_path)
    data=json.loads(target.read_text())
    assert data['mcpServers']['other']['command']=='other' and data['custom']
    assert data['mcpServers']['jev-skills']['type']=='stdio'
    assert Path(result['backup']).exists()

def test_cursor_conflict_no_write(tmp_path):
    target=tmp_path/'.cursor/mcp.json';target.parent.mkdir();old='{"mcpServers":{"jev-skills":{"command":"existing"}}}';target.write_text(old)
    with pytest.raises(RouterError):install_client('cursor',tmp_path/'config.json',home=tmp_path)
    assert target.read_text()==old

@pytest.mark.parametrize('field,value',[('min_fit',2),('max_skills',0),('shortlist',True),('mode','auto'),('roots','bad'),('max_concurrency',0),('max_concurrency',9),('max_concurrency',True),('route_timeout_seconds',0),('route_timeout_seconds',float('nan'))])
def test_invalid_config_rejected(field,value):
    with pytest.raises(RouterError):Config(**{field:value}).validate()

def test_invalid_config_json(tmp_path):
    file=tmp_path/'config.json';file.write_text('[]')
    with pytest.raises(RouterError):Config.load(file)

def test_hook_missing_config_does_not_block_user_prompt(tmp_path):
    process=subprocess.run([sys.executable,'-m','jev_skill_router','--config',str(tmp_path/'absent.json'),'hook'],input='{"prompt":"Debug Python"}',capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},timeout=15)
    assert process.returncode==0
    result=json.loads(process.stdout)
    assert result['hookSpecificOutput']['hookEventName']=='UserPromptSubmit'
    assert 'No skill was selected' in result['hookSpecificOutput']['additionalContext']
    assert result.get('decision')!='block'

def test_measurement_uses_real_catalog_without_api(skill_root):
    from jev_skill_router.measurement import measure
    result=measure(Config(roots=[str(skill_root)]),'python-debug')
    assert result['model_calls']==0 and result['selected_payload_bytes']>0
    assert result['unit']=='UTF-8 bytes, not model tokens'
    assert result['one_context_reduction_percent']<0

def test_unknown_tool_argument_rejected(skill_root):
    router=Router(Config(roots=[str(skill_root)],mode='offline'))
    with pytest.raises(RouterError):dispatch(router,{'action':'route','task':'Debug Python','execute':True})

def test_malformed_restore_manifest(tmp_path):
    file=tmp_path/'migration.json';file.write_text('[]')
    with pytest.raises(RouterError):restore(file)

def test_installer_help_has_no_mutations(tmp_path):
    process=subprocess.run([sys.executable,str(ROOT/'Install.py'),'--help'],capture_output=True,text=True,env={**os.environ,'JEV_SKILLS_HOME':str(tmp_path/'home')},timeout=10)
    assert process.returncode==0 and '--offline' in process.stdout
    assert not (tmp_path/'home').exists()

def test_publisher_requires_explicit_visibility():
    process=subprocess.run([sys.executable,str(ROOT/'scripts/publish_github.py')],capture_output=True,text=True,timeout=10)
    assert process.returncode==2 and '--public' in process.stderr
