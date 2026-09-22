from __future__ import annotations
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
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
    update(data)
    backup=None
    if path.exists():
        backup=path.with_name(path.name+f'.jev-backup-{time.time_ns()}');shutil.copy2(path,backup)
    atomic_json(path,data)
    return str(backup) if backup else None

def install_client(client:str,config_file:Path,home:Path|None=None,hook:bool=False)->dict:
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
        bridge=home/('.claude/skills' if client=='claude' else '.agents/skills')/'jev-skill-router/SKILL.md'
        from .catalog import Catalog
        Catalog._no_symlinks(bridge)
        if bridge.exists() and bridge.read_text(encoding='utf-8')!=SKILL:
            raise RouterError('An edited router bridge already exists; it was not overwritten')
        executable=shutil.which(client)
        if not executable: raise RouterError(f'{client} CLI is not on PATH. Use jev-skills config-snippet.')
        args=([executable,'mcp','add','--transport','stdio','--scope','user','jev-skills','--'] if client=='claude'
              else [executable,'mcp','add','jev-skills','--'])+cmd
        result=subprocess.run(args,capture_output=True,text=True)
        if result.returncode: raise RouterError(f'{client} registration failed. Check its MCP list; an existing entry may need removal.')
        bridge=home/('.claude/skills' if client=='claude' else '.agents/skills')/'jev-skill-router/SKILL.md'
        if bridge.exists() and bridge.read_text(encoding='utf-8')!=SKILL:
            raise RouterError('An edited router bridge already exists; it was not overwritten')
        bridge.parent.mkdir(parents=True,exist_ok=True);bridge.write_text(SKILL,encoding='utf-8')
        out={'registered':client,'bridge':str(bridge)}
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
        out['hook_backup']=merge_json(home/'.claude/settings.json',hook_update)
    return out
