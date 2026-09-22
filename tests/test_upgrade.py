"""Regression coverage for preserving existing installations and host state."""
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from jev_skill_router.config import RouterError
from jev_skill_router import integrations

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def installer():
    spec=importlib.util.spec_from_file_location('jev_guided_installer',ROOT/'Install.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def existing_install(tmp_path):
    app=tmp_path/'custom-app';runtime=app/'runtime';runtime.mkdir(parents=True)
    (runtime/'pyvenv.cfg').write_text('version = 3.11\n')
    config=app/'config.json'
    config.write_text('{"roots": ["/trusted/parked"], "mode": "offline", "max_skills": 2}\n')
    (app/'bin').mkdir();(app/'bin/jev-skills').write_text('existing launcher')
    return app,config


def test_guided_upgrade_preserves_configuration_and_registration(installer,tmp_path,monkeypatch):
    app,config=existing_install(tmp_path);original=config.read_bytes()
    monkeypatch.setenv('JEV_SKILLS_HOME',str(app))
    calls=[];monkeypatch.setattr(installer,'run',lambda args:calls.append(args))
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    monkeypatch.setattr(installer.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout=version+'\n'))
    assert installer.main(['--upgrade','--non-interactive','--no-keychain'])==0
    assert config.read_bytes()==original
    assert (app/'bin/jev-skills').read_text()=='existing launcher'
    assert not (app/'example-skills').exists()
    assert len(calls)==2 and 'pip' in calls[0] and calls[1][-1]=='doctor'
    assert not any(word in call for call in calls for word in ['setup','auth','mcp'])
    assert str(app/'runtime') in calls[0][0]


def test_guided_rerun_requires_explicit_upgrade_before_any_install(installer,tmp_path,monkeypatch):
    app,config=existing_install(tmp_path);original=config.read_bytes()
    monkeypatch.setenv('JEV_SKILLS_HOME',str(app))
    monkeypatch.setattr(installer,'run',lambda args:pytest.fail('must not install'))
    with pytest.raises(SystemExit) as error:installer.main(['--non-interactive','--offline'])
    assert error.value.code==2 and config.read_bytes()==original


@pytest.mark.parametrize('flag',[['--offline'],['--root','/new'],['--client','none'],['--auth'],['--hook']])
def test_upgrade_rejects_configuration_changing_options(installer,tmp_path,monkeypatch,flag):
    monkeypatch.setenv('JEV_SKILLS_HOME',str(tmp_path/'absent'))
    with pytest.raises(SystemExit) as error:installer.main(['--upgrade',*flag])
    assert error.value.code==2 and not (tmp_path/'absent').exists()


def test_upgrade_refuses_unverified_package_version(installer,tmp_path,monkeypatch):
    app,config=existing_install(tmp_path);original=config.read_bytes()
    monkeypatch.setenv('JEV_SKILLS_HOME',str(app))
    calls=[];monkeypatch.setattr(installer,'run',lambda args:calls.append(args))
    monkeypatch.setattr(installer.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='0.0.0\n'))
    with pytest.raises(RuntimeError,match='version'):installer.main(['--upgrade','--non-interactive'])
    assert len(calls)==1 and config.read_bytes()==original


def test_cursor_repeated_install_is_noop(tmp_path):
    cfg=tmp_path/'router.json'
    first=integrations.install_client('cursor',cfg,home=tmp_path)
    file=Path(first['file']);before=file.read_bytes();stat=file.stat()
    second=integrations.install_client('cursor',cfg,home=tmp_path)
    assert second['backup'] is None and file.read_bytes()==before
    assert file.stat().st_mtime_ns==stat.st_mtime_ns
    assert not list(file.parent.glob('*.jev-backup-*'))


@pytest.mark.parametrize('client',['codex','claude'])
def test_existing_matching_cli_registration_preserved(client,tmp_path,monkeypatch):
    cfg=tmp_path/'router.json';cmd=integrations.command(cfg)
    path,bridge,_=integrations._client_paths(client,tmp_path);path.parent.mkdir(parents=True)
    if client=='codex':
        text='[mcp_servers.jev-skills]\ncommand = '+json.dumps(cmd[0])+'\nargs = '+json.dumps(cmd[1:])+'\nenv_vars = ["TYPESAFE_API_KEY"]\nstartup_timeout_sec = 35\n'
    else:text=json.dumps({'custom':'keep','mcpServers':{'jev-skills':{'command':cmd[0],'args':cmd[1:],'env':{'EXTRA':'keep'}}}})
    path.write_text(text);bridge.parent.mkdir(parents=True);bridge.write_text(integrations.SKILL)
    monkeypatch.setattr(integrations.shutil,'which',lambda name:'/host/'+name)
    monkeypatch.setattr(integrations.subprocess,'run',lambda *args,**kwargs:pytest.fail('matching registration must not invoke add'))
    result=integrations.install_client(client,cfg,home=tmp_path)
    assert result['status']=='already_registered' and path.read_text()==text


@pytest.mark.parametrize('client',['codex','claude'])
def test_conflicting_cli_registration_not_overwritten(client,tmp_path,monkeypatch):
    path,bridge,_=integrations._client_paths(client,tmp_path);path.parent.mkdir(parents=True)
    text='[mcp_servers.jev-skills]\ncommand="other"\n' if client=='codex' else '{"mcpServers":{"jev-skills":{"command":"other"}}}'
    path.write_text(text)
    monkeypatch.setattr(integrations.shutil,'which',lambda name:'/host/'+name)
    monkeypatch.setattr(integrations.subprocess,'run',lambda *a,**kw:pytest.fail('must not overwrite'))
    with pytest.raises(RouterError,match='not overwritten'):integrations.install_client(client,tmp_path/'router.json',home=tmp_path)
    assert path.read_text()==text and not bridge.exists()


def test_codex_key_forwarding_adds_name_only_and_preserves_other_settings(tmp_path,monkeypatch):
    path=tmp_path/'config.toml'
    path.write_text('model = "custom"\n[mcp_servers.other]\ncommand = "other"\n[mcp_servers.jev-skills]\ncommand = "python"\nargs = ["-m", "jev_skill_router"]\n')
    monkeypatch.setenv('TYPESAFE_API_KEY','this-must-not-be-written')
    integrations._codex_forward_key(path)
    text=path.read_text();data=tomllib.loads(text)
    assert data['model']=='custom' and data['mcp_servers']['other']['command']=='other'
    assert data['mcp_servers']['jev-skills']['env_vars']==['TYPESAFE_API_KEY']
    assert 'this-must-not-be-written' not in text
    before=text;integrations._codex_forward_key(path);assert path.read_text()==before


def test_explicit_test_home_isolates_host_profiles(tmp_path,monkeypatch):
    monkeypatch.setenv('CODEX_HOME','/user/codex')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR','/user/claude')
    codex,_,codex_env=integrations._client_paths('codex',tmp_path)
    claude,_,claude_env=integrations._client_paths('claude',tmp_path)
    assert codex==tmp_path/'.codex/config.toml' and claude==tmp_path/'.claude/.claude.json'
    assert codex_env['CODEX_HOME']==str(tmp_path/'.codex')
    assert claude_env['CLAUDE_CONFIG_DIR']==str(tmp_path/'.claude')
    assert os.environ['CODEX_HOME']=='/user/codex' and os.environ['CLAUDE_CONFIG_DIR']=='/user/claude'


@pytest.mark.parametrize('client',['codex','claude'])
def test_new_cli_registration_uses_isolated_profile_and_verifies_saved_entry(client,tmp_path,monkeypatch):
    cfg=tmp_path/'router.json';cmd=integrations.command(cfg)
    path,bridge,_=integrations._client_paths(client,tmp_path)
    monkeypatch.setattr(integrations.shutil,'which',lambda name:'/host/'+name)
    def register(args,**kwargs):
        assert path.parent.is_dir()
        profile_key='CODEX_HOME' if client=='codex' else 'CLAUDE_CONFIG_DIR'
        assert Path(kwargs['env'][profile_key])==path.parent
        assert kwargs['timeout']==30
        if client=='codex':
            path.write_text('[mcp_servers.jev-skills]\ncommand = '+json.dumps(cmd[0])+'\nargs = '+json.dumps(cmd[1:])+'\n')
        else:path.write_text(json.dumps({'mcpServers':{'jev-skills':{'type':'stdio','command':cmd[0],'args':cmd[1:]}}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(integrations.subprocess,'run',register)
    result=integrations.install_client(client,cfg,home=tmp_path)
    assert result['status']=='registered' and bridge.read_text()==integrations.SKILL
    if client=='codex':assert tomllib.loads(path.read_text())['mcp_servers']['jev-skills']['env_vars']==['TYPESAFE_API_KEY']


def test_edited_bridge_prevents_registration(tmp_path,monkeypatch):
    _,bridge,_=integrations._client_paths('codex',tmp_path)
    bridge.parent.mkdir(parents=True);bridge.write_text('Custom user instructions')
    monkeypatch.setattr(integrations.subprocess,'run',lambda *a,**kw:pytest.fail('bridge must be checked before registration'))
    with pytest.raises(RouterError,match='edited router bridge'):
        integrations.install_client('codex',tmp_path/'router.json',home=tmp_path)
    assert bridge.read_text()=='Custom user instructions'


def test_launcher_binds_custom_config_without_environment(installer,tmp_path):
    app=tmp_path/'custom app';executable=app/'runtime/bin/python'
    launcher=installer.write_launcher(app,executable)
    text=launcher.read_text()
    assert '--config' in text and str(app/'config.json') in text and ' -I ' in text
    # An application-owned old launcher is migrated; a user's edit is preserved.
    launcher.write_text('custom user launcher\n')
    installer.write_launcher(app,executable)
    assert launcher.read_text()=='custom user launcher\n'
