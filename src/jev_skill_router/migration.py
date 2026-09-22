"""Explicit, reversible relocation out of harness-discovered skills/ folders."""
from __future__ import annotations
import json
import shutil
import uuid
from pathlib import Path
from .catalog import Catalog
from .config import Config,RouterError,atomic_json,home_dir

def park(source:Path,config:Config,config_file:Path,apply:bool=False,vault:Path|None=None)->dict:
    source=source.expanduser().absolute();Catalog._no_symlinks(source)
    if source.name!='skills' or not source.is_dir():
        raise RouterError('park accepts an existing directory named skills, not your home or project root')
    vault=(vault or home_dir()/'vault').expanduser().absolute()
    Catalog._no_symlinks(vault)
    if vault.resolve().is_relative_to(source.resolve()):
        raise RouterError('Vault must be outside the original skills tree')
    candidates=[p for p in sorted(source.iterdir()) if p.is_dir() and not p.is_symlink() and not p.name.startswith('.') and p.name!='jev-skill-router' and (p/'SKILL.md').is_file()]
    if not candidates: raise RouterError('No direct, movable skills found; nested/plugin-managed collections are not moved automatically')
    destination=vault/uuid.uuid4().hex
    operations=[{'source':str(p),'destination':str(destination/p.name)} for p in candidates]
    result={'dry_run':not apply,'operations':operations,'note':'Built-in .system, the router bridge, nested collections, and plugin-managed registries are untouched. Start a new host session after changing exposure.'}
    if not apply: return result
    destination.mkdir(parents=True)
    manifest=destination/'migration.json'
    record={'state':'moving','operations':operations,'old_roots':list(config.roots),'config_file':str(config_file.absolute())}
    atomic_json(manifest,record)
    moved=[]
    try:
        for op in operations:
            shutil.move(op['source'],op['destination']);moved.append(op)
        config.roots=list(dict.fromkeys([*config.roots,str(destination)]));config.save(config_file)
        record['state']='parked';atomic_json(manifest,record)
    except Exception as e:
        for op in reversed(moved):
            if Path(op['destination']).exists() and not Path(op['source']).exists(): shutil.move(op['destination'],op['source'])
        config.roots=record['old_roots'];config.save(config_file)
        record['state']='rolled_back';atomic_json(manifest,record)
        raise RouterError(f'Migration failed; rollback attempted. Inspect {manifest}') from e
    result['manifest']=str(manifest);return result

def restore(manifest:Path,apply:bool=False)->dict:
    manifest=manifest.expanduser().absolute();Catalog._no_symlinks(manifest)
    try: record=json.loads(manifest.read_text(encoding='utf-8'))
    except (ValueError,OSError) as e: raise RouterError('Cannot read migration manifest') from e
    if not isinstance(record,dict) or record.get('state')!='parked' or not isinstance(record.get('operations'),list): raise RouterError('Manifest is not in parked state')
    operations=record['operations']
    if not operations or not isinstance(record.get('config_file'),str): raise RouterError('Incomplete manifest')
    config_file=Path(record['config_file'])
    if not config_file.is_absolute(): raise RouterError('Manifest config path must be absolute')
    Catalog._no_symlinks(config_file)
    for op in operations:
        if not isinstance(op,dict) or set(op)!={'source','destination'} or not all(isinstance(v,str) for v in op.values()): raise RouterError('Invalid migration entry')
        source=Path(op['source']);destination=Path(op['destination'])
        Catalog._no_symlinks(source);Catalog._no_symlinks(destination)
        if not source.is_absolute() or source.parent.name!='skills' or destination.parent!=manifest.parent or destination.name!=source.name:
            raise RouterError('Unsafe migration manifest paths')
        if source.exists(): raise RouterError('Restore would overwrite an existing skill; resolve the conflict first')
        if not destination.is_dir(): raise RouterError('Parked skill is missing')
    result={'dry_run':not apply,'operations':operations}
    if not apply:return result
    config_file=Path(record['config_file'])
    config=Config.load(config_file);original_roots=list(config.roots);moved=[]
    try:
        for op in operations:
            Path(op['source']).parent.mkdir(parents=True,exist_ok=True)
            shutil.move(op['destination'],op['source']);moved.append(op)
        # Preserve roots added after parking instead of restoring an obsolete entire configuration.
        config.roots=list(dict.fromkeys([r for r in config.roots if Path(r).expanduser().absolute()!=manifest.parent]+[str(Path(op['source']).parent) for op in operations]))
        config.save(config_file)
        record['state']='restored';atomic_json(manifest,record)
    except Exception as e:
        for op in reversed(moved):
            if Path(op['source']).exists() and not Path(op['destination']).exists(): shutil.move(op['source'],op['destination'])
        config.roots=original_roots;config.save(config_file)
        raise RouterError('Restore failed; rollback attempted. Inspect the manifest and both directories.') from e
    return result
