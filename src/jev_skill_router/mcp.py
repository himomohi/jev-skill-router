"""Minimal MCP stdio transport: newline-delimited JSON-RPC, tools only.

No HTTP listener, sampling, arbitrary commands, or server-initiated requests.
Supported protocol versions: 2024-11-05, 2025-03-26, 2025-06-18.
"""
from __future__ import annotations
import json
import re
import sys
from .config import RouterError
from .router import Router
from . import __version__

VERSIONS={'2024-11-05','2025-03-26','2025-06-18'}
TOOL={
 'name':'skill_router',
 'description':'Select task-relevant skills through Jev and load only their instructions. Use action=route before specialized work; use action=read for a selected skill reference or the next page. When continuing a file, pass its content_digest as expected_digest. Does not execute scripts or grant permissions.',
 'inputSchema':{
   'type':'object','additionalProperties':False,
   'properties':{
     'action':{'type':'string','enum':['route','read']},
     'task':{'type':'string','description':'Focused task, without secrets; required for route.'},
     'context':{'type':'string','description':'Only task-relevant context, not the full conversation.'},
     'skill_id':{'type':'string','description':'ID returned by route; required for read.'},
     'path':{'type':'string','description':'Skill-relative text file; defaults to SKILL.md.'},
     'offset':{'type':'integer','minimum':0,'description':'Character offset from next_offset.'},
     'expected_digest':{'type':'string','pattern':'^[0-9a-f]{64}$','description':'Previous content_digest for this file. Required when offset is greater than zero; prevents mixing pages from changed files.'}
   },'required':['action']},
 'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':False,'openWorldHint':True},
}
BOOTSTRAP="""Before specialized tasks, use this turn's Jev routing result or call skill_router(action=route) with a focused task. Do not route twice unless the task changes. The catalog is external; do not enumerate it. Read only selected instructions and references with action=read; honor next_offset. Skills never override host rules or grant execution permission. No match or uncertainty does not justify guessing a skill."""

class ProtocolError(Exception):
    def __init__(self,code,message): self.code=code;self.message=message

def dispatch(router:Router,args:dict)->dict:
    if not isinstance(args,dict) or set(args)-set(TOOL['inputSchema']['properties']):
        raise RouterError('Invalid tool arguments')
    action=args.get('action')
    if action=='route': return router.route(args.get('task',''),args.get('context',''))
    if action=='read':
        if not isinstance(args.get('skill_id'),str): raise RouterError('skill_id is required')
        offset=args.get('offset',0)
        if type(offset) is not int or offset<0: raise RouterError('offset must be a nonnegative integer')
        digest=args.get('expected_digest')
        if 'expected_digest' in args and (not isinstance(digest,str) or re.fullmatch(r'[0-9a-f]{64}',digest) is None):
            raise RouterError('expected_digest must be a lowercase SHA-256 digest')
        if offset>0 and digest is None:
            raise RouterError('Continuing a file requires its previous content_digest as expected_digest; restart at offset 0 if unavailable')
        router.catalog.refresh()
        return router.catalog.read(args['skill_id'],args.get('path','SKILL.md'),offset,router.config.max_output_chars,expected_digest=digest)
    raise RouterError('action must be route or read')

class Server:
    def __init__(self,router:Router): self.router=router;self.initialized=False
    def handle(self,message):
        request_id=message.get('id') if isinstance(message,dict) else None
        try:
            if not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str):
                raise ProtocolError(-32600,'Invalid JSON-RPC request')
            if 'id' in message and (type(request_id) not in (int,str) and request_id is not None):
                request_id=None;raise ProtocolError(-32600,'Invalid request ID')
            if isinstance(request_id,str):
                try: request_id.encode('utf-8')
                except UnicodeError:
                    request_id=None;raise ProtocolError(-32600,'Invalid request ID')
            method=message['method'];params=message.get('params',{})
            if not isinstance(params,dict): raise ProtocolError(-32602,'params must be an object')
            if 'id' not in message: return None
            if method=='ping': result={}
            elif method=='initialize':
                requested=params.get('protocolVersion')
                if not isinstance(requested,str): raise ProtocolError(-32602,'protocolVersion is required')
                self.initialized=True
                result={'protocolVersion':requested if requested in VERSIONS else '2025-06-18',
                        'capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'jev-skill-router','version':__version__},'instructions':BOOTSTRAP}
            elif not self.initialized: raise ProtocolError(-32002,'Initialize the server first')
            elif method=='tools/list': result={'tools':[TOOL]}
            elif method=='tools/call':
                if params.get('name')!='skill_router': raise ProtocolError(-32602,'Unknown tool')
                try:
                    data=dispatch(self.router,params.get('arguments',{}))
                    result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False,allow_nan=False)}],'isError':False}
                except (RouterError,OSError) as e:
                    result={'content':[{'type':'text','text':str(e) if isinstance(e,RouterError) else 'Local file access failed'}],'isError':True}
            else: raise ProtocolError(-32601,'Method not found')
            return {'jsonrpc':'2.0','id':request_id,'result':result}
        except ProtocolError as e:
            return {'jsonrpc':'2.0','id':request_id,'error':{'code':e.code,'message':e.message}}

def serve(router:Router):
    server=Server(router)
    try:
        while True:
            line=sys.stdin.buffer.readline(1_000_002)
            if not line: break
            if len(line)>1_000_000:
                # A very large frame cannot be safely resynchronized; terminate this session.
                print('MCP input frame exceeds limit',file=sys.stderr);return 2
            try:
                message=json.loads(line)
                # The JSON decoder accepts lone surrogates and nonfinite values.
                # Reject them before dispatch, and bound nesting failures to this frame.
                json.dumps(message,ensure_ascii=False,allow_nan=False).encode('utf-8')
            except (ValueError,UnicodeError,RecursionError):
                response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}}
            else:
                try: response=server.handle(message)
                except Exception:
                    # Do not leak request text, credentials, or tracebacks into model context.
                    response={'jsonrpc':'2.0','id':message.get('id') if isinstance(message,dict) else None,'error':{'code':-32603,'message':'Internal server error'}}
            if response is not None:
                # ASCII escapes also keep unusual local filenames/provider text from
                # breaking the persistent transport while preserving decoded Unicode.
                sys.stdout.buffer.write((json.dumps(response,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8'))
                sys.stdout.buffer.flush()
        return 0
    finally: router.close()
