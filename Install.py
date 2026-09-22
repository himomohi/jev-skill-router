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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', action='append', help='Trusted directory containing SKILL.md folders')
    parser.add_argument('--client', choices=['none','claude','codex','cursor'])
    parser.add_argument('--offline', action='store_true', help='Explicit keyword demo, without Jev')
    parser.add_argument('--hook', action='store_true', help='Opt-in Claude pre-turn routing')
    parser.add_argument('--auth', action='store_true', help='Prompt for a key and store it in OS keychain')
    parser.add_argument('--verify', action='store_true', help='Make one real TypeSafe API diagnostic request')
    parser.add_argument('--no-keychain', action='store_true', help='Install core dependencies only; use environment credentials')
    parser.add_argument('--non-interactive', action='store_true')
    args = parser.parse_args()
    if sys.version_info < (3,11):
        parser.error('Python 3.11 or newer is required.')
    if args.hook and args.client not in {None,'claude'}:
        parser.error('--hook is only available with Claude Code.')
    interactive = sys.stdin.isatty() and not args.non_interactive
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
    if runtime.exists() and not (runtime/'pyvenv.cfg').is_file():
        parser.error('Runtime path exists but is not a Python virtual environment. It was not changed.')
    print('Installing into:',runtime)
    if not runtime.exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    executable=runtime/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    package=str(ROOT)+('' if args.no_keychain else '[secure]')
    run([str(executable),'-m','pip','install','--disable-pip-version-check',package])
    if not roots:
        destination=home/'example-skills'
        if not destination.exists():shutil.copytree(ROOT/'examples/skills',destination)
        roots=[str(destination)]
        print('Using bundled examples. Add your own trusted library with setup --root PATH.')
    prefix=[str(executable),'-m','jev_skill_router']
    setup=prefix+['setup']
    for root in roots:setup+=['--root',str(Path(root).expanduser().resolve())]
    if args.offline:setup+=['--offline']
    if client!='none':setup+=['--client',client]
    if args.hook:setup+=['--hook']
    run(setup)
    if args.auth:run(prefix+['auth'])
    if args.verify:run(prefix+['doctor','--live'])
    else:run(prefix+['doctor'])
    bindir=home/'bin';bindir.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        launcher=bindir/'jev-skills.cmd'
        launcher.write_text('@echo off\r\n"'+str(executable)+'" -m jev_skill_router %*\r\n')
    else:
        launcher=bindir/'jev-skills'
        launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(executable))+' -m jev_skill_router "$@"\n')
        launcher.chmod(0o755)
    print('\nInstalled. CLI launcher:',launcher)
    print('Add that bin directory to PATH, or run the launcher using its full path.')
    print('Native skill exposure has NOT been disabled. Review park (dry run), or disable native copies; then start a NEW host session.')
    if not args.offline and not args.auth:
        print('Live mode requires TYPESAFE_API_KEY in the server environment or the auth command.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (subprocess.CalledProcessError,OSError) as exc:
        print(f'Installation did not complete ({type(exc).__name__}). Review the output; no skills were moved.',file=sys.stderr)
        raise SystemExit(1)
