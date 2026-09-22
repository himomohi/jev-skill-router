from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import yaml
from .config import RouterError

MAX_FILE_BYTES=512_000
TEXT_SUFFIXES={".md",".txt",".py",".js",".mjs",".cjs",".ts",".tsx",".jsx",".json",".yaml",".yml",".toml",".sh",".ps1",".html",".css",".csv",".sql",".r",".rs",".go",".swift"}
BLOCKED_NAMES={"credentials.json","secrets.json","secrets.yaml","id_rsa","id_ed25519","token.json"}

@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    directory: Path
    source: Path
    body: str
    digest: str
    def metadata(self) -> dict:
        return {"id":self.id,"name":self.name,"description":self.description}

class Catalog:
    def __init__(self, roots: list[str], limit: int = 4096):
        self.roots=[Path(x).expanduser().absolute() for x in roots]
        self.limit=limit
        self.skills: dict[str,Skill]={}
        self.warnings: list[str]=[]
        self.refresh()

    @staticmethod
    def _no_symlinks(path: Path) -> None:
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise RouterError("Symbolic links are not accepted in skill paths")

    @staticmethod
    def _text(path: Path) -> str:
        Catalog._no_symlinks(path)
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise RouterError("Skill file is missing or exceeds 512 KB")
        try:
            with path.open("rb") as f:
                raw=f.read(MAX_FILE_BYTES+1)
            if len(raw)>MAX_FILE_BYTES or b"\0" in raw:
                raise ValueError()
            return raw.decode("utf-8-sig")
        except (UnicodeError,ValueError,OSError) as e:
            raise RouterError("Only bounded UTF-8 text files are supported") from e

    def refresh(self) -> None:
        skills={};warnings=[];seen=set()
        for root in self.roots:
            try:
                self._no_symlinks(root)
                if not root.is_dir(): raise RouterError("root is not a directory")
            except RouterError as e:
                warnings.append(f"{root}: {e}");continue
            for current,dirs,files in os.walk(root,followlinks=False):
                here=Path(current)
                dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in {'node_modules','__pycache__','venv'} and not (here/d).is_symlink())
                if 'SKILL.md' not in files: continue
                file=here/'SKILL.md'
                if file.absolute() in seen: continue
                seen.add(file.absolute())
                try:
                    text=self._text(file)
                    lines=text.splitlines()
                    if not lines or lines[0].strip()!='---': raise RouterError("missing YAML frontmatter")
                    end=next((i for i,s in enumerate(lines[1:],1) if s.strip()=='---'),None)
                    if end is None or end>200: raise RouterError("invalid or oversized frontmatter")
                    meta=yaml.safe_load('\n'.join(lines[1:end]))
                    if not isinstance(meta,dict): raise RouterError("frontmatter must be a mapping")
                    name,description=meta.get('name'),meta.get('description')
                    if not isinstance(name,str) or not 1<=len(name)<=64: raise RouterError("invalid name")
                    if not isinstance(description,str) or not 1<=len(description)<=1024: raise RouterError("invalid description")
                    sid='s_'+hashlib.sha256(str(file.absolute()).encode()).hexdigest()[:16]
                    body='\n'.join(lines[end+1:]).strip()
                    skills[sid]=Skill(sid,name,description.strip(),here.absolute(),file.absolute(),body,hashlib.sha256(text.encode()).hexdigest())
                    if len(skills)>self.limit: raise RouterError("Catalog exceeds configured max_catalog_skills")
                except (RouterError,yaml.YAMLError,OSError,RecursionError) as e:
                    if len(skills)>self.limit: raise RouterError("Catalog exceeds configured max_catalog_skills") from e
                    warnings.append(f"{file}: invalid or unsupported skill ({type(e).__name__})")
        self.skills=dict(sorted(skills.items(),key=lambda x:(x[1].name,str(x[1].source))))
        self.warnings=warnings
        self.fingerprint=hashlib.sha256(json.dumps([(s.id,s.digest) for s in self.skills.values()]).encode()).hexdigest()

    def read(self, skill_id: str, path: str = 'SKILL.md', offset: int = 0, limit: int = 12000) -> dict:
        skill=self.skills.get(skill_id)
        if not skill: raise RouterError("Unknown skill ID. Route a task to obtain an ID.")
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50000:
            raise RouterError("Invalid read range")
        if not isinstance(path,str) or not path or '\\' in path or Path(path).is_absolute() or PureWindowsPath(path).drive:
            raise RouterError("Only skill-relative paths are permitted")
        rel=Path(path)
        if any(p in {'..','.'} or p.startswith('.') for p in rel.parts):
            raise RouterError("Hidden files and parent traversal are not permitted")
        if rel.name.lower() in BLOCKED_NAMES or rel.suffix.lower() not in TEXT_SUFFIXES:
            raise RouterError("Secret-like names and unsupported file types are blocked")
        target=skill.directory/rel
        self._no_symlinks(target)
        if not target.resolve().is_relative_to(skill.directory.resolve()):
            raise RouterError("Path escapes the skill directory")
        text=self._text(target)
        if offset>len(text): raise RouterError("Offset is beyond the end of the file")
        end=min(len(text),offset+limit)
        return {"skill_id":skill.id,"name":skill.name,"path":path,"content":text[offset:end],"offset":offset,"next_offset":end if end<len(text) else None,"total_chars":len(text),"base_directory":str(skill.directory)}
