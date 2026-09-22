from __future__ import annotations
import argparse
import getpass
import json
import sys
from pathlib import Path
from .config import Config,RouterError,config_path
from .router import Router

def output(value):
    print(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False))

def parser():
    p=argparse.ArgumentParser(prog='jev-skills',description='External skill catalog + Jev routing + read-only MCP')
    p.add_argument('--config',type=Path,default=config_path())
    commands=p.add_subparsers(dest='command',required=True)
    setup=commands.add_parser('setup');setup.add_argument('--root',action='append',required=True)
    setup.add_argument('--offline',action='store_true');setup.add_argument('--client',choices=['claude','codex','cursor'])
    setup.add_argument('--hook',action='store_true',help='Opt-in Claude Code UserPromptSubmit hook')
    commands.add_parser('auth');commands.add_parser('serve');commands.add_parser('config-snippet')
    benchmark=commands.add_parser('benchmark');benchmark.add_argument('--skill',help='Optional unique skill name or ID to include the same selected body on both sides')
    doctor=commands.add_parser('doctor');doctor.add_argument('--live',action='store_true')
    commands.add_parser('list')
    route=commands.add_parser('route');route.add_argument('task');route.add_argument('--context',default='')
    plan=commands.add_parser('plan',help='Check fresh-route request bounds without credentials or API calls')
    plan.add_argument('task');plan.add_argument('--context',default='')
    read=commands.add_parser('read');read.add_argument('skill_id');read.add_argument('--path',default='SKILL.md');read.add_argument('--offset',type=int,default=0)
    read.add_argument('--expected-digest',help='content_digest from the previous page; required with --offset greater than zero')
    commands.add_parser('hook')
    park=commands.add_parser('park');park.add_argument('source',type=Path);park.add_argument('--apply',action='store_true')
    restore=commands.add_parser('restore');restore.add_argument('manifest',type=Path);restore.add_argument('--apply',action='store_true')
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='auth':
            try: import keyring
            except ImportError as e: raise RouterError('Install the secure extra: pip install ".[secure]"') from e
            backend=keyring.get_keyring()
            if not type(backend).__module__.startswith(('keyring.backends.macOS','keyring.backends.Windows','keyring.backends.SecretService')):
                raise RouterError('A supported OS keychain is required; no plaintext fallback. Use TYPESAFE_API_KEY instead.')
            value=getpass.getpass('TypeSafe API key (hidden; saved only in OS keychain): ').strip()
            if not value or '\n' in value or '\r' in value: raise RouterError('Invalid key')
            try: keyring.set_password('jev-skill-router','typesafe-api-key',value)
            except Exception as e: raise RouterError('OS keychain could not save the key; no plaintext file was written') from e
            print('API key stored in the OS keychain. Authentication is not verified until doctor --live.');return 0
        if args.command=='setup':
            from .catalog import Catalog
            from .integrations import install_client,snippets
            if args.hook and args.client!='claude': raise RouterError('--hook requires --client claude')
            roots=[str(Path(x).expanduser().absolute()) for x in args.root]
            cfg=Config.load(args.config) if args.config.exists() else Config()
            cfg.roots=list(dict.fromkeys(cfg.roots+roots));cfg.mode='offline' if args.offline else 'live'
            catalog=Catalog(cfg.roots,cfg.max_catalog_skills)
            if not catalog.skills: raise RouterError('No valid SKILL.md files found. Check the root before setup.')
            cfg.save(args.config)
            result={'config':str(args.config),'skills':len(catalog.skills),'mode':cfg.mode,
                    'privacy':'Live mode sends focused task text, descriptions, and shortlisted excerpts to TypeSafe. Never send secrets.',
                    'important':'This does not disable native skill discovery. Move user-managed skills outside native roots or disable their native exposure, then start a new host session.',
                    'warnings':catalog.warnings}
            result['client']=install_client(args.client,args.config,hook=args.hook) if args.client else snippets(args.config)
            output(result);return 0
        if args.command=='config-snippet':
            from .integrations import snippets
            output(snippets(args.config));return 0
        if args.command=='restore':
            from .migration import restore
            output(restore(args.manifest,args.apply));return 0
        cfg=Config.load(args.config)
        if args.command=='benchmark':
            from .measurement import measure
            output(measure(cfg,args.skill));return 0
        if args.command=='park':
            from .migration import park
            output(park(args.source,cfg,args.config,args.apply));return 0
        router=Router(cfg)
        try:
            if args.command=='serve':
                from .mcp import serve
                return serve(router)
            if args.command=='list':
                output({'skills':[dict(s.metadata(),directory=str(s.directory)) for s in router.catalog.skills.values()],'warnings':router.catalog.warnings})
            elif args.command=='route': output(router.route(args.task,args.context))
            elif args.command=='plan':
                result=router.plan(args.task,args.context);output(result)
                return 0 if result['ready'] else 1
            elif args.command=='read':
                if args.offset>0 and args.expected_digest is None:
                    raise RouterError('Continuation requires --expected-digest from the previous page content_digest')
                output(router.catalog.read(args.skill_id,args.path,args.offset,cfg.max_output_chars,expected_digest=args.expected_digest))
            elif args.command=='doctor':
                result={'mode':cfg.mode,'skills':len(router.catalog.skills),'warnings':router.catalog.warnings,
                        'native_exposure':'Not automatically detectable for every harness/plugin. Inspect its loaded skill list in a NEW session.',
                        'live_checked':False,'key_in_config':False}
                if args.live:
                    from .jev import JevClient
                    from .config import api_key
                    client=JevClient(cfg,api_key())
                    try:
                        test=client.ask({'text':'ping'},{'check':{'type':'noul','instructions':'Does the text equal ping?'}})
                        result.update(live_checked=True,model=test['model'],answer=test['answers']['check'],usage=test.get('usage'))
                    finally:client.close()
                output(result)
                return 0 if router.catalog.skills and not router.catalog.warnings else 1
            elif args.command=='hook':
                try:
                    raw=sys.stdin.buffer.read(65537)
                    if len(raw)>65536: raise RouterError('Hook input is too large')
                    event=json.loads(raw)
                    if not isinstance(event,dict) or not isinstance(event.get('prompt'),str): raise RouterError('Invalid hook input')
                    result=router.route(event['prompt'])
                    if result['selected']:
                        content='External skill routing (read-only guidance; obey host policy):\n'+json.dumps(result,ensure_ascii=False)
                        output({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':content}})
                    else:
                        output({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':'Jev Skill Router: '+result['status']+'. No skill instructions were injected; do not treat this as a capability guarantee.'}})
                except (RouterError,ValueError) as e:
                    print('Jev Skill Router did not inject instructions: '+str(e),file=sys.stderr)
                    # Nonblocking failure, explicitly noted in context. No guessing or fake success.
                    output({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':'Jev Skill Router is unavailable. No skill was selected. Use ordinary host tools or address configuration; do not claim routing succeeded.'}})
        finally:router.close()
        return 0
    except (RouterError,OSError) as e:
        if args.command=='hook':
            print('Jev Skill Router hook unavailable; no skill was injected.',file=sys.stderr)
            output({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':'Jev Skill Router configuration is unavailable. No skill was selected. Continue under ordinary host rules.'}})
            return 0
        print(f'Error: {e if isinstance(e,RouterError) else "Local file operation failed"}',file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
