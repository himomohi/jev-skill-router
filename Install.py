#!/usr/bin/env python3
"""Guided, user-local installation. Requires Python 3.11+ and package-index access."""
from __future__ import annotations
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def write_launcher(home: Path, executable: Path) -> Path:
    """Keep the launcher bound to its installation even without shell variables."""
    bindir=home/'bin';bindir.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        launcher=bindir/'jev-skills.cmd'
        original='@echo off\n"'+str(executable)+'" -m jev_skill_router %*\n'
        content='@echo off\n"'+str(executable)+'" -I -m jev_skill_router --config "'+str(home/'config.json')+'" %*\n'
    else:
        launcher=bindir/'jev-skills'
        original='#!/bin/sh\nexec '+shlex.quote(str(executable))+' -m jev_skill_router "$@"\n'
        content='#!/bin/sh\nexec '+shlex.quote(str(executable))+' -I -m jev_skill_router --config '+shlex.quote(str(home/'config.json'))+' "$@"\n'
    if launcher.is_symlink():
        print('Existing symlinked launcher was preserved:',launcher)
        return launcher
    if launcher.exists() and launcher.read_text(encoding='utf-8') not in {original,content}:
        print('Existing custom launcher was preserved:',launcher)
        return launcher
    launcher.write_text(content,encoding='utf-8',newline='\r\n' if os.name=='nt' else '\n')
    if os.name!='nt':launcher.chmod(0o755)
    return launcher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade', action='store_true', help='Upgrade the existing private runtime, preserving configuration and client registration')
    parser.add_argument('--root', action='append', help='Trusted directory containing SKILL.md folders')
    parser.add_argument('--client', choices=['none','claude','codex','cursor'])
    parser.add_argument('--offline', action='store_true', help='Explicit keyword demo, without Jev')
    parser.add_argument('--hook', action='store_true', help='Opt-in Claude pre-turn routing')
    parser.add_argument('--auth', action='store_true', help='Prompt for a key and store it in OS keychain')
    parser.add_argument('--verify', action='store_true', help='Make one real TypeSafe API diagnostic request')
    parser.add_argument('--no-keychain', action='store_true', help='Install core dependencies only; use environment credentials')
    parser.add_argument('--non-interactive', action='store_true')
    args = parser.parse_args(argv)
    if sys.version_info < (3,11):
        parser.error('Python 3.11 or newer is required.')
    if args.hook and args.client not in {None,'claude'}:
        parser.error('--hook is only available with Claude Code.')
    if args.upgrade and (args.root or args.client is not None or args.offline or args.hook or args.auth):
        parser.error('--upgrade preserves roots, mode, client registration and credentials; do not combine it with setup options.')
    interactive = sys.stdin.isatty() and not args.non_interactive and not args.upgrade
    roots = args.root or []
    if interactive and not roots:
        value = input('Skill folder (Enter = bundled examples): ').strip()
        if value: roots=[value]
    client = args.client
    if client is None and interactive:
        client = input('Connect client [claude / codex / cursor / none] (none): ').strip().lower() or 'none'
    client = client or 'none'
    if client not in {'claude','codex','cursor','none'}:
        parser.error('Unknown client')
    if args.hook and client!='claude':
        parser.error('--hook requires Claude Code.')
    home=Path(os.environ.get('JEV_SKILLS_HOME','~/.jev-skill-router')).expanduser().resolve()
    runtime=home/'runtime'
    config_file=home/'config.json'
    if runtime.is_symlink():
        parser.error('Runtime path is a symlink. It was not changed.')
    if config_file.exists() and not args.upgrade:
        parser.error('An existing configuration was found. Use --upgrade to preserve it; use the setup command for deliberate configuration changes.')
    if args.upgrade and (not config_file.is_file() or not (runtime/'pyvenv.cfg').is_file()):
        parser.error('--upgrade requires an existing guided installation and config.json in JEV_SKILLS_HOME.')
    if runtime.exists() and not (runtime/'pyvenv.cfg').is_file():
        parser.error('Runtime path exists but is not a Python virtual environment. It was not changed.')
    print('Upgrading:' if args.upgrade else 'Installing into:',runtime)
    if not runtime.exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    executable=runtime/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    package=str(ROOT)+('' if args.no_keychain else '[secure]')
    run([str(executable),'-I','-m','pip','install','--upgrade','--disable-pip-version-check',package])
    import tomllib
    expected=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    check=subprocess.run([str(executable),'-I','-c',
        'from importlib.metadata import version; print(version("jev-skill-router"))'],
        check=True,capture_output=True,text=True)
    installed=check.stdout.strip()
    if installed!=expected:
        raise RuntimeError('Installed package version does not match this checkout; installation is not verified.')
    print('Verified installed package version:',installed)
    prefix=[str(executable),'-I','-m','jev_skill_router','--config',str(config_file)]
    if args.upgrade:
        run(prefix+['doctor']+(['--live'] if args.verify else []))
        write_launcher(home,executable)
        print('Upgrade complete. Existing roots, mode, credentials and client registration were preserved.')
        print('Restart your host session so it starts the upgraded server.')
        return 0
    if not roots:
        destination=home/'example-skills'
        if not destination.exists():shutil.copytree(ROOT/'examples/skills',destination)
        roots=[str(destination)]
        print('Using bundled examples. Add your own trusted library with setup --root PATH.')
    setup=prefix+['setup']
    for root in roots:setup+=['--root',str(Path(root).expanduser().resolve())]
    if args.offline:setup+=['--offline']
    if client!='none':setup+=['--client',client]
    if args.hook:setup+=['--hook']
    run(setup)
    if args.auth:run(prefix+['auth'])
    if args.verify:run(prefix+['doctor','--live'])
    else:run(prefix+['doctor'])
    launcher=write_launcher(home,executable)
    print('\nInstalled. CLI launcher:',launcher)
    print('Add that bin directory to PATH, or run the launcher using its full path.')
    print('Native skill exposure has NOT been disabled. Review park (dry run), or disable native copies; then start a NEW host session.')
    if not args.offline and not args.auth:
        print('Live mode requires TYPESAFE_API_KEY in the server environment or the auth command.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (subprocess.CalledProcessError,OSError,RuntimeError) as exc:
        print(f'Installation did not complete ({type(exc).__name__}). Review the output; no skills were moved.',file=sys.stderr)
        raise SystemExit(1)
