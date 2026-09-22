#!/usr/bin/env python3
"""Check an actual host CLI using disposable profiles and no model/API requests.

Run with the same Python environment as the installed router. This validates host
registration, connection through the host MCP client, and a real server protocol
round-trip. It does not prove model selection/task success.
"""
from __future__ import annotations
import argparse
import json
import os
import queue
import re
import threading
import time
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jev_skill_router.config import Config, RouterError
from jev_skill_router.integrations import install_client, _client_paths


def codex_connection(executable:str,env:dict,scratch:Path)->None:
    """Ask Codex's own MCP client to discover the server, without starting a turn."""
    process=subprocess.Popen([executable,'app-server'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
         stderr=subprocess.DEVNULL,text=True,env=env,cwd=scratch)
    received=queue.Queue()
    def read_output():
        for line in process.stdout:received.put(line)
        received.put(None)
    threading.Thread(target=read_output,daemon=True).start()
    def request(identifier,method,params):
        process.stdin.write(json.dumps({'id':identifier,'method':method,'params':params})+'\n');process.stdin.flush()
        deadline=time.monotonic()+30
        while True:
            try:line=received.get(timeout=max(0.01,deadline-time.monotonic()))
            except queue.Empty as exc:raise RouterError('Codex MCP discovery timed out') from exc
            if line is None:raise RouterError('Codex app-server closed before discovery finished')
            message=json.loads(line)
            if message.get('id')==identifier:
                if 'error' in message:raise RouterError('Codex app-server rejected MCP discovery')
                return message['result']
    try:
        request(1,'initialize',{'clientInfo':{'name':'jev-host-check','version':'1'}})
        process.stdin.write('{"method":"initialized"}\n');process.stdin.flush()
        result=request(2,'mcpServerStatus/list',{})
        server=next((item for item in result.get('data',[]) if item.get('name')=='jev-skills'),None)
        if not server or 'skill_router' not in server.get('tools',{}):
            raise RouterError('Codex MCP client did not discover skill_router')
    finally:
        if process.poll() is None:
            process.stdin.close()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        process.stdout.close()


def run_check(client:str)->dict:
    executable=shutil.which(client)
    result={'client':client,'available':bool(executable),'model_calls':0,
            'live_jev_checked':False,'host_model_task_checked':False,
            'profile':'disposable temporary directory'}
    if not executable:
        return {**result,'status':'unavailable','reason':f'{client} CLI is not on PATH'}
    with tempfile.TemporaryDirectory(prefix='jev-host-check-') as directory:
        scratch=Path(directory)
        skill=scratch/'external-skills/python-debug';skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('---\nname: python-debug\ndescription: Debug Python code and tracebacks.\n---\nInspect the traceback and reproduce the failure before making a fix.\n',encoding='utf-8')
        cfg=scratch/'router.json';Config(roots=[str(skill.parent)],mode='offline').save(cfg)
        host_config,_,env=_client_paths(client,scratch)
        # Scrub common provider keys. Offline protocol checks do not need them.
        for key in list(env):
            if any(marker in key for marker in ('API_KEY','AUTH_TOKEN','OAUTH_TOKEN')):env.pop(key,None)
        version=subprocess.run([executable,'--version'],capture_output=True,text=True,env=env,cwd=scratch,timeout=20)
        if version.returncode:raise RouterError('Host version check failed')
        result['version']=version.stdout.strip().splitlines()[0]
        installed=install_client(client,cfg,home=scratch)
        before=host_config.read_bytes()
        repeated=install_client(client,cfg,home=scratch)
        result['registration_verified']=installed['status']=='registered'
        result['repeat_preserved_config']=repeated['status']=='already_registered' and before==host_config.read_bytes()
        args=[executable,'mcp','get','jev-skills']+(['--json'] if client=='codex' else [])
        get=subprocess.run(args,capture_output=True,text=True,env=env,cwd=scratch,timeout=30)
        if get.returncode:raise RouterError('Host MCP lookup failed')
        if client=='codex':
            details=json.loads(get.stdout)
            transport=details.get('transport',{})
            if transport.get('command')!=sys.executable or 'TYPESAFE_API_KEY' not in transport.get('env_vars',[]):
                raise RouterError('Codex did not report the expected command/key forwarding')
            codex_connection(executable,env,scratch)
            result['host_connection_checked']=True
            result['host_connection_method']='Codex app-server mcpServerStatus/list'
        else:
            result['host_connection_checked']=bool(re.search(r'\bConnected\b',get.stdout))
            result['host_connection_method']='Claude mcp get connection status'
            if not result['host_connection_checked']:
                raise RouterError('Claude did not confirm an MCP connection')
        frames=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'host-check','version':'1'}}},
                {'jsonrpc':'2.0','method':'notifications/initialized'},
                {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'skill_router','arguments':{'action':'route','task':'Debug Python code traceback'}}}]
        process=subprocess.Popen([sys.executable,'-m','jev_skill_router','--config',str(cfg),'serve'],
             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,cwd=scratch)
        received=queue.Queue()
        def read_output():
            for line in process.stdout:received.put(line)
            received.put(None)
        reader=threading.Thread(target=read_output,daemon=True);reader.start()
        try:
            process.stdin.write('\n'.join(json.dumps(frame) for frame in frames)+'\n');process.stdin.flush()
            replies={};deadline=time.monotonic()+20
            while 3 not in replies:
                try:line=received.get(timeout=max(0.01,deadline-time.monotonic()))
                except queue.Empty as exc:raise RouterError('Server protocol response timed out') from exc
                if line is None:raise RouterError('Server closed before answering the route request')
                message=json.loads(line)
                if 'id' in message:replies[message['id']]=message
            process.stdin.close()
            process.wait(timeout=5)
            if process.returncode:raise RouterError('Server protocol subprocess failed')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close();process.stderr.close()
        tools=replies[2]['result']['tools']
        route=json.loads(replies[3]['result']['content'][0]['text'])
        if [tool['name'] for tool in tools]!=['skill_router'] or route['selected'][0]['name']!='python-debug':
            raise RouterError('Server did not expose the expected tool and route')
        result.update(status='passed',protocol_roundtrip_verified=True)
        return result


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',choices=['codex','claude'],required=True)
    args=parser.parse_args(argv)
    try:
        result=run_check(args.client)
    except (RouterError,OSError,ValueError,KeyError,IndexError,subprocess.TimeoutExpired) as exc:
        result={'client':args.client,'status':'failed','reason':str(exc) if isinstance(exc,RouterError) else type(exc).__name__,
                'model_calls':0,'host_model_task_checked':False}
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
