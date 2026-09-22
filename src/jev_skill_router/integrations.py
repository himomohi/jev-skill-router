from __future__ import annotations
import json
import os
import re
import tempfile
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from .config import RouterError,atomic_json
from .mcp import BOOTSTRAP

SKILL="""---
name: jev-skill-router
description: Select and load specialized skill instructions from an external library via the skill_router MCP tool. Use before specialized tasks rather than scanning a large catalog.
---

"""+BOOTSTRAP+'\n'

def command(config_file:Path)->list[str]:
    return [sys.executable,'-m','jev_skill_router','--config',str(config_file.absolute()),'serve']

def snippets(config_file:Path)->dict:
    cmd=command(config_file)
    return {'json':{'mcpServers':{'jev-skills':{'command':cmd[0],'args':cmd[1:]}}},
            'codex_toml':'[mcp_servers.jev-skills]\ncommand = '+json.dumps(cmd[0])+'\nargs = '+json.dumps(cmd[1:])+'\nenv_vars = ["TYPESAFE_API_KEY"]\n',
            'bootstrap':BOOTSTRAP}

def merge_json(path:Path,update):
    if path.is_symlink(): raise RouterError('Refusing to overwrite a symlinked client configuration')
    try: data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (ValueError,OSError) as e: raise RouterError('Existing client config is not readable JSON; it was not changed') from e
    if not isinstance(data,dict): raise RouterError('Existing client config must be a JSON object')
    previous=json.dumps(data,sort_keys=True)
    update(data)
    if path.exists() and previous==json.dumps(data,sort_keys=True):return None
    backup=None
    if path.exists():
        backup=path.with_name(path.name+f'.jev-backup-{time.time_ns()}');shutil.copy2(path,backup)
    atomic_json(path,data)
    return str(backup) if backup else None

def _client_paths(client:str,home:Path|None)->tuple[Path,Path,dict]:
    """Honor host profile settings; an explicit home isolates all host writes."""
    base=home if home is not None else Path.home()
    env=dict(os.environ)
    if client=='codex':
        profile=(base/'.codex') if home is not None else Path(env.get('CODEX_HOME',str(base/'.codex'))).expanduser()
        if home is not None:env['CODEX_HOME']=str(profile)
        return profile/'config.toml',base/'.agents/skills/jev-skill-router/SKILL.md',env
    profile=(base/'.claude') if home is not None else Path(env.get('CLAUDE_CONFIG_DIR',str(base/'.claude'))).expanduser()
    if home is not None:env['CLAUDE_CONFIG_DIR']=str(profile)
    config=(profile/'.claude.json') if home is not None or env.get('CLAUDE_CONFIG_DIR') else base/'.claude.json'
    return config,profile/'skills/jev-skill-router/SKILL.md',env


def _existing_registration(client:str,path:Path,cmd:list[str])->bool:
    """Inspect only the matching entry. Never print credentials or replace conflicts."""
    if not path.exists():return False
    try:
        raw=path.read_text(encoding='utf-8')
        data=tomllib.loads(raw) if client=='codex' else json.loads(raw)
        if not isinstance(data,dict):raise ValueError()
        servers=data.get('mcp_servers' if client=='codex' else 'mcpServers',{})
        if not isinstance(servers,dict):raise ValueError()
        entry=servers.get('jev-skills')
        if entry is None:return False
        if (not isinstance(entry,dict) or entry.get('command')!=cmd[0] or entry.get('args',[])!=cmd[1:]
            or entry.get('type','stdio')!='stdio' or entry.get('url') is not None):
            raise RouterError('jev-skills already exists with another configuration; it was not overwritten')
        if entry.get('enabled') is False:
            raise RouterError('The existing jev-skills registration is disabled. Enable it explicitly in the host configuration.')
        return True
    except (ValueError,OSError) as exc:
        raise RouterError('Existing client configuration is not readable; it was not changed') from exc


def _codex_forward_key(path:Path)->None:
    """Allow inherited credentials by name without ever writing their value."""
    raw=path.read_text(encoding='utf-8')
    parsed=tomllib.loads(raw)
    entry=parsed['mcp_servers']['jev-skills']
    if 'TYPESAFE_API_KEY' in entry.get('env_vars',[]):return
    # Called only for a newly created CLI entry. Avoid rewriting arbitrary TOML.
    header=re.compile(r'(?m)^\[mcp_servers\.(?:jev-skills|"jev-skills"|\'jev-skills\')\][ \t]*(?:#[^\n]*)?$')
    match=header.search(raw)
    if not match or 'env_vars' in entry:
        raise RouterError('Codex registered the server, but API-key forwarding needs manual configuration. Use config-snippet.')
    updated=raw[:match.end()]+'\nenv_vars = ["TYPESAFE_API_KEY"]'+raw[match.end():]
    expected=json.loads(json.dumps(parsed));expected['mcp_servers']['jev-skills']['env_vars']=['TYPESAFE_API_KEY']
    if tomllib.loads(updated)!=expected:
        raise RouterError('Codex API-key forwarding could not be verified. Use config-snippet.')
    backup=path.with_name(path.name+f'.jev-backup-{time.time_ns()}');shutil.copy2(path,backup)
    fd,name=tempfile.mkstemp(prefix='.jev-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as file:
            file.write(updated);file.flush();os.fsync(file.fileno())
        if path.read_text(encoding='utf-8')!=raw:
            raise RouterError('Codex configuration changed during registration. Retry after the other writer finishes.')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def install_client(client:str,config_file:Path,home:Path|None=None,hook:bool=False)->dict:
    requested_home=home
    home=home or Path.home();cmd=command(config_file);out={}
    if hook and client!='claude': raise RouterError('The automatic hook is supported only for Claude Code')
    if client=='cursor':
        path=home/'.cursor/mcp.json'
        def update(data):
            servers=data.setdefault('mcpServers',{})
            if not isinstance(servers,dict): raise RouterError('mcpServers must be an object')
            if 'jev-skills' in servers and servers['jev-skills']!={'type':'stdio','command':cmd[0],'args':cmd[1:]}:
                raise RouterError('jev-skills already exists with another configuration; it was not overwritten')
            servers['jev-skills']={'type':'stdio','command':cmd[0],'args':cmd[1:]}
        out={'file':str(path),'backup':merge_json(path,update)}
        # Cursor rules are not silently rewritten. The tool description still supports on-demand use.
    elif client in {'claude','codex'}:
        host_config,bridge,env=_client_paths(client,requested_home)
        from .catalog import Catalog
        Catalog._no_symlinks(host_config)
        Catalog._no_symlinks(bridge)
        if bridge.exists() and bridge.read_text(encoding='utf-8')!=SKILL:
            raise RouterError('An edited router bridge already exists; it was not overwritten')
        executable=shutil.which(client)
        if not executable: raise RouterError(f'{client} CLI is not on PATH. Use jev-skills config-snippet.')
        args=([executable,'mcp','add','--transport','stdio','--scope','user','jev-skills','--'] if client=='claude'
              else [executable,'mcp','add','jev-skills','--'])+cmd
        existing=_existing_registration(client,host_config,cmd)
        if not existing:
            host_config.parent.mkdir(parents=True,exist_ok=True)
            try:result=subprocess.run(args,capture_output=True,text=True,env=env,timeout=30)
            except subprocess.TimeoutExpired as exc:raise RouterError(f'{client} registration timed out. Check its MCP list before retrying.') from exc
            if result.returncode: raise RouterError(f'{client} registration failed. Check its MCP list; an existing entry may need removal.')
            if client=='codex':_codex_forward_key(host_config)
            if not _existing_registration(client,host_config,cmd):
                raise RouterError(f'{client} returned success but its registration could not be verified. Check its MCP list.')
        if bridge.exists() and bridge.read_text(encoding='utf-8')!=SKILL:
            raise RouterError('An edited router bridge already exists; it was not overwritten')
        if not bridge.exists():
            bridge.parent.mkdir(parents=True,exist_ok=True);bridge.write_text(SKILL,encoding='utf-8')
        out={'registered':client,'bridge':str(bridge),'status':'already_registered' if existing else 'registered'}
    else: raise RouterError('Supported clients: claude, codex, cursor')
    if hook:
        if client!='claude': raise RouterError('The automatic hook is supported only for Claude Code')
        hook_cmd=[sys.executable,'-m','jev_skill_router','--config',str(config_file.absolute()),'hook']
        shell_command=subprocess.list2cmdline(hook_cmd) if os.name=='nt' else shlex.join(hook_cmd)
        entry={'hooks':[{'type':'command','command':shell_command,'timeout':120}]}
        def hook_update(data):
            all_hooks=data.setdefault('hooks',{})
            if not isinstance(all_hooks,dict): raise RouterError('hooks must be an object')
            hooks=all_hooks.setdefault('UserPromptSubmit',[])
            if not isinstance(hooks,list): raise RouterError('UserPromptSubmit hooks must be an array')
            if entry not in hooks: hooks.append(entry)
        out['hook_backup']=merge_json(bridge.parents[2]/'settings.json',hook_update)
    return out
