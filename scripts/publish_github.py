"""Create a NEW GitHub repo from this reviewed source, using the user's gh login.

Requires Git + GitHub CLI, gh auth login, and an existing Git author identity.
Never overwrites a repository, force-pushes, or borrows credentials from another app.
"""
from __future__ import annotations
import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOW={'.gitignore','.github','src','tests','docs','scripts','examples','video','README.md','README.ko.md',
       'pyproject.toml','LICENSE','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','CHANGELOG.ko.md','Install.py','Install.cmd','Install.command'}
SECRET_PATTERNS=[re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
                 re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
                 re.compile(r'\bgithub_pat_[A-Za-z0-9_]{40,}\b'),
                 re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b')]


def run(command:list[str],check:bool=True)->subprocess.CompletedProcess:
    return subprocess.run(command,cwd=ROOT,text=True,capture_output=True,check=check)


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    visibility=parser.add_mutually_exclusive_group(required=True)
    visibility.add_argument('--public',action='store_true')
    visibility.add_argument('--private',action='store_true')
    parser.add_argument('--name',default='jev-skill-router')
    parser.add_argument('--release',action='store_true',help='Also create a release for the current source version, including historical video previews')
    args=parser.parse_args()
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    notes=ROOT/f'docs/updates/v{version}.md'
    if args.release and (not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version) or not notes.is_file()):
        parser.error('Current version release notes are required before publication.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',args.name):parser.error('Invalid repository name')
    if not shutil.which('git') or not shutil.which('gh'):parser.error('Install Git and GitHub CLI, then run gh auth login.')
    run(['gh','auth','status'])
    login=run(['gh','api','user','--jq','.login']).stdout.strip()
    if not re.fullmatch(r'[A-Za-z0-9-]+',login):parser.error('Unexpected GitHub login')
    target=f'{login}/{args.name}'
    if run(['gh','repo','view',target,'--json','name'],check=False).returncode==0:
        parser.error(f'{target} already exists; refusing to overwrite or publish into it.')
    for key in ('user.name','user.email'):
        if not run(['git','config','--get',key],check=False).stdout.strip():
            parser.error(f'Configure your Git {key} before publishing. No identity was invented.')
    current=run(['git','rev-parse','--show-toplevel'],check=False)
    if current.returncode==0 and Path(current.stdout.strip()).resolve()!=ROOT:
        parser.error('This folder is inside another Git repository; extract it outside that repository first.')
    if (ROOT/'.git').exists() and run(['git','remote'],check=False).stdout.strip():
        parser.error('A remote already exists. Review it and publish manually; no remote was changed.')
    candidates=[]
    for top in sorted(ALLOW):
        path=ROOT/top
        if not path.exists():continue
        files=sorted(path.rglob('*')) if path.is_dir() else [path]
        for file in files:
            relative=file.relative_to(ROOT)
            if any(part.endswith('.egg-info') for part in relative.parts):continue
            if any(part in {'__pycache__','node_modules','.pytest_cache','.venv','out','dist','build'} for part in relative.parts):continue
            if file.is_symlink():parser.error(f'Symlink not allowed in publishing bundle: {relative}')
            if not file.is_file():continue
            if file.suffix in {'.pyc','.pyo','.log'} or file.name.startswith('.env'):continue
            if file.stat().st_size>40_000_000:parser.error(f'File exceeds 40 MB publishing guard: {relative}')
            if file.suffix not in {'.mp4','.png','.jpg','.gif','.webp'}:
                try:content=file.read_text(encoding='utf-8')
                except UnicodeError:parser.error(f'Unexpected binary file: {relative}')
                if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                    parser.error(f'Possible credential in {relative}. Review it; no content was printed.')
            candidates.append(str(relative))
    # This scan covers a few recognizable credential formats, not every secret.
    # Publish only after personally reviewing local modifications and sensitive text.
    if not (ROOT/'.git').exists():run(['git','init','-b','main'])
    tracked=run(['git','ls-files']).stdout.splitlines()
    if any(path not in candidates for path in tracked):parser.error('Unexpected tracked files are present; review them before publishing.')
    # Avoid platform argv limits by staging bounded batches.
    for i in range(0,len(candidates),50):run(['git','add','--',*candidates[i:i+50]])
    if run(['git','diff','--cached','--quiet'],check=False).returncode:
        run(['git','commit','-m','Initial Jev skill routing implementation, tests, docs and media'])
    print('Creating:',target,flush=True)
    result=run(['gh','repo','create',target,'--public' if args.public else '--private','--source','.',
                '--remote','origin','--push','--description','External skill catalog + Jev selection + one read-only MCP tool'])
    print(result.stdout)
    if args.release:
        assets=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'docs/media').glob('*.mp4'))]
        if not assets:parser.error('No video files are present for the release.')
        sha=run(['git','rev-parse','HEAD']).stdout.strip()
        release=run(['gh','release','create',f'v{version}',*assets,'--repo',target,'--target',sha,
                     '--title',f'Jev Skill Router {version}','--notes-file',str(notes)])
        print(release.stdout)
    print('Published repository:',f'https://github.com/{target}')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f'Publishing stopped at {exc.cmd[0]} (exit {exc.returncode}). Check gh auth status and the local git state. No force-push was attempted.',file=sys.stderr)
        raise SystemExit(1)
