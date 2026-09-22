"""Minimal MCP stdio transport: newline-delimited JSON-RPC, tools only.

No HTTP listener, sampling, arbitrary commands, or server-initiated requests.
Supported protocol versions: 2024-11-05, 2025-03-26, 2025-06-18.
"""
from __future__ import annotations
import json
import re
import sys
import threading
from collections import deque
from .config import RouterError
from .jev import CancellationToken, RoutingCancelled
from .router import Router
from . import __version__

VERSIONS={'2024-11-05','2025-03-26','2025-06-18'}
MAX_PENDING_CALLS=16
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

def dispatch(router:Router,args:dict,*,cancellation:CancellationToken|None=None)->dict:
    if cancellation is not None: cancellation.check()
    if not isinstance(args,dict) or set(args)-set(TOOL['inputSchema']['properties']):
        raise RouterError('Invalid tool arguments')
    action=args.get('action')
    if action=='route':
        return router.route(args.get('task',''),args.get('context',''),cancellation=cancellation)
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
        if cancellation is not None: cancellation.check()
        return router.catalog.read(args['skill_id'],args.get('path','SKILL.md'),offset,router.config.max_output_chars,expected_digest=digest)
    raise RouterError('action must be route or read')

class Server:
    def __init__(self,router:Router): self.router=router;self.initialized=False
    def handle(self,message,*,cancellation=None,submit=None,cancel=None):
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
            if method=='notifications/cancelled' and 'id' not in message:
                # Cancellation is fire-and-forget, including malformed/unknown IDs.
                if cancel is not None and isinstance(params,dict): cancel(params)
                return None
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
                if submit is not None: return submit(message)
                try:
                    data=dispatch(self.router,params.get('arguments',{}),cancellation=cancellation)
                    result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False,allow_nan=False)}],'isError':False}
                except RoutingCancelled:
                    return None
                except (RouterError,OSError) as e:
                    result={'content':[{'type':'text','text':str(e) if isinstance(e,RouterError) else 'Local file access failed'}],'isError':True}
            else: raise ProtocolError(-32601,'Method not found')
            return {'jsonrpc':'2.0','id':request_id,'result':result}
        except ProtocolError as e:
            return {'jsonrpc':'2.0','id':request_id,'error':{'code':e.code,'message':e.message}}

def _internal_error(message):
    return {'jsonrpc':'2.0','id':message.get('id') if isinstance(message,dict) else None,
            'error':{'code':-32603,'message':'Internal server error'}}


class _ToolWorker:
    """One owner for Router/cache/HTTP state; the reader only manages tokens.

    There are at most MAX_PENDING_CALLS accepted calls including the active one.
    EOF cancels all accepted work, and closes the pool on this same worker.
    """

    def __init__(self,server,emit):
        self.server=server
        self.emit=emit
        self.condition=threading.Condition()
        self.queue=deque()
        self.pending={}
        self.stopped=False
        self.cleanup_failed=False
        self.thread=threading.Thread(target=self._run,name='jev-mcp-tools')
        self.thread.start()

    def submit(self,message):
        request_id=message['id']
        with self.condition:
            if request_id in self.pending:
                raise ProtocolError(-32600,'Request ID is already in progress')
            if self.stopped or len(self.pending)>=MAX_PENDING_CALLS:
                raise ProtocolError(-32000,'Tool request queue is full; wait for an earlier request to finish')
            token=CancellationToken()
            self.pending[request_id]=token
            self.queue.append((message,token))
            self.condition.notify()
        return None

    def cancel(self,params):
        request_id=params.get('requestId')
        if type(request_id) not in (int,str): return
        if 'reason' in params and not isinstance(params['reason'],str): return
        with self.condition:
            token=self.pending.get(request_id)
            if token is None: return
            # Drop cancelled queued calls immediately to free the bounded slot.
            for queued,queued_token in self.queue:
                if queued_token is token:
                    self.queue.remove((queued,queued_token))
                    self.pending.pop(request_id,None)
                    break
            token.cancel()

    def stop(self):
        with self.condition:
            self.stopped=True
            self.queue.clear()
            for token in self.pending.values(): token.cancel()
            self.condition.notify_all()

    def close(self):
        self.stop()
        self.thread.join()

    def _run(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda:self.queue or self.stopped)
                    if self.stopped: return
                    message,token=self.queue.popleft()
                response=None
                try:
                    if not token.cancelled:
                        response=self.server.handle(message,cancellation=token)
                except Exception:
                    response=_internal_error(message)
                try:
                    # The spec suppresses responses for successfully cancelled calls.
                    if not token.cancelled and response is not None:
                        if not self.emit(response): self.stop()
                finally:
                    with self.condition:
                        self.pending.pop(message['id'],None)
        finally:
            try: self.server.router.close()
            except Exception:
                self.cleanup_failed=True
                print('MCP resource cleanup failed',file=sys.stderr)


def serve(router:Router):
    server=Server(router)
    output_lock=threading.Lock()
    def emit(response):
        # Both paths may reply, but one complete JSON frame is always written.
        try:
            data=(json.dumps(response,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8')
            with output_lock:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            return True
        except (OSError,ValueError):
            return False
    worker=_ToolWorker(server,emit)
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
                try: response=server.handle(message,submit=worker.submit,cancel=worker.cancel)
                except Exception:
                    # Do not leak request text, credentials, or tracebacks into model context.
                    response=_internal_error(message)
            if response is not None:
                # ASCII escapes also keep unusual local filenames/provider text from
                # breaking the persistent transport while preserving decoded Unicode.
                if not emit(response): break
    finally: worker.close()
    return 2 if worker.cleanup_failed else 0
