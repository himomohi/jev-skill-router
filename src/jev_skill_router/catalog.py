from __future__ import annotations
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
import yaml
from .config import RouterError
from .evidence import json_width_counts
from .windows_metadata import change_stamp as windows_change_stamp

MAX_FILE_BYTES=512_000
TEXT_SUFFIXES={".md",".txt",".py",".js",".mjs",".cjs",".ts",".tsx",".jsx",".json",".yaml",".yml",".toml",".sh",".ps1",".html",".css",".csv",".sql",".r",".rs",".go",".swift"}
BLOCKED_NAMES={"credentials.json","secrets.json","secrets.yaml","id_rsa","id_ed25519","token.json"}
# The native bridge is retained on disk for the host, but must never route to itself.
RESERVED_SKILL_NAMES={'jev-skill-router'}
# Windows needs native change time; st_ctime there can be creation time.
STAT_CACHE_SUPPORTED=True

@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    directory: Path
    source: Path
    body: str
    digest: str
    body_json_width_counts: tuple[int,...] = field(init=False,repr=False)
    def __post_init__(self) -> None:
        object.__setattr__(self,'body_json_width_counts',json_width_counts(self.body))
    def metadata(self) -> dict:
        return {"id":self.id,"name":self.name,"description":self.description}

class Catalog:
    def __init__(self, roots: list[str], limit: int = 4096):
        self.roots=[Path(x).expanduser().absolute() for x in roots]
        self.limit=limit
        self.skills: dict[str,Skill]={}
        self.warnings: list[str]=[]
        self._file_cache: dict[Path,tuple[tuple[int,...],Skill]]={}
        self.refresh_stats: dict[str,int]={}
        self.refresh()

    @staticmethod
    def _is_redirect(path: Path) -> bool:
        try:
            info=path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return True  # An uninspectable path cannot be considered safe.
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info,'st_file_attributes',0) & 0x400)

    @staticmethod
    def _no_symlinks(path: Path) -> None:
        if any(Catalog._is_redirect(p) for p in (path, *path.parents)):
            raise RouterError("Symbolic links and reparse points are not accepted in skill paths")

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

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int,...]:
        # Check the whole path even on a cache hit: a previously safe directory
        # may since have been replaced by a symbolic link.
        Catalog._no_symlinks(path)
        info=path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise RouterError("Skill file is missing or exceeds 512 KB")
        native=windows_change_stamp(path) if os.name=='nt' else (info.st_ctime_ns,)
        # A zero final component marks an unsupported metadata query. Such
        # entries may be parsed but must never be reused on the next refresh.
        return (info.st_dev,info.st_ino,info.st_mode,info.st_size,
                info.st_mtime_ns,*(native or ()),int(native is not None))

    def refresh(self, *, force: bool = False) -> None:
        """Rescan paths and reuse unchanged parsed files, without a TTL.

        Identity, size, mode and nanosecond modification/change timestamps are
        checked on each scan. ``force=True`` re-reads and hashes every file for
        filesystems whose metadata cannot reliably expose content changes. The
        Windows optimization uses native change time on NTFS/ReFS; unavailable
        queries fall back to full reads. This is not protection against hostile metadata spoofing. The read
        tool always reads the current file, independently of this cache.
        """
        skills={};warnings=[];seen=set();seen_roots=set();file_cache={}
        stats={'files_seen':0,'files_reused':0,'files_reloaded':0}
        for root in self.roots:
            try:
                self._no_symlinks(root)
                if not root.is_dir(): raise RouterError("root is not a directory")
                # Inspect the original spelling first so normalization cannot
                # hide a symlink/reparse component followed by parent traversal.
                root=root.resolve(strict=True)
            except (RouterError,OSError) as e:
                warnings.append(f"{root}: {e}");continue
            if root in seen_roots: continue
            seen_roots.add(root)
            def unreadable_directory(error):
                warnings.append(f"{error.filename or root}: unreadable skill directory")
            for current,dirs,files in os.walk(root,followlinks=False,onerror=unreadable_directory):
                here=Path(current)
                dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in {'node_modules','__pycache__','venv'} and not self._is_redirect(here/d))
                if 'SKILL.md' not in files: continue
                file=here/'SKILL.md'
                if file.absolute() in seen: continue
                seen.add(file.absolute())
                stats['files_seen']+=1
                try:
                    stamp=self._file_stamp(file)
                    cached=self._file_cache.get(file.absolute())
                    # An absent inode cannot reliably identify replacements.
                    if STAT_CACHE_SUPPORTED and not force and stamp[1] and stamp[-1] and cached and cached[0]==stamp:
                        skill=cached[1]
                        file_cache[file.absolute()]=cached
                        stats['files_reused']+=1
                        if skill.name in RESERVED_SKILL_NAMES: continue
                        skills[skill.id]=skill
                        if len(skills)>self.limit: raise RouterError("Catalog exceeds configured max_catalog_skills")
                        continue
                    stats['files_reloaded']+=1
                    text=self._text(file)
                    if self._file_stamp(file)!=stamp:
                        raise RouterError("Skill file changed while being read; retry refresh")
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
                    skill=Skill(sid,name,description.strip(),here.absolute(),file.absolute(),body,hashlib.sha256(text.encode()).hexdigest())
                    file_cache[file.absolute()]=(stamp,skill)
                    if skill.name in RESERVED_SKILL_NAMES: continue
                    skills[sid]=skill
                    if len(skills)>self.limit: raise RouterError("Catalog exceeds configured max_catalog_skills")
                except (RouterError,yaml.YAMLError,OSError,RecursionError) as e:
                    if len(skills)>self.limit: raise RouterError("Catalog exceeds configured max_catalog_skills") from e
                    # RouterError contains our fixed safe diagnostics. YAML
                    # exceptions can quote source text; never expose those.
                    reason=str(e) if isinstance(e,RouterError) else (
                        'invalid YAML frontmatter' if isinstance(e,yaml.YAMLError) else
                        'frontmatter nesting is too deep' if isinstance(e,RecursionError) else
                        'skill file could not be read')
                    warnings.append(f"{file}: {reason}")
        self.skills=dict(sorted(skills.items(),key=lambda x:(x[1].name,str(x[1].source))))
        self.warnings=warnings
        self._file_cache=file_cache
        self.refresh_stats=stats
        self.fingerprint=hashlib.sha256(json.dumps([(s.id,s.digest) for s in self.skills.values()]).encode()).hexdigest()

    def read(self, skill_id: str, path: str = 'SKILL.md', offset: int = 0, limit: int = 12000, *, expected_digest: str | None = None) -> dict:
        skill=self.skills.get(skill_id)
        if not skill: raise RouterError("Unknown skill ID. Route a task to obtain an ID.")
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50000:
            raise RouterError("Invalid read range")
        if expected_digest is not None and (not isinstance(expected_digest,str) or
                len(expected_digest)!=64 or any(c not in '0123456789abcdef' for c in expected_digest)):
            raise RouterError("expected_digest must be a lowercase SHA-256 content digest")
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
        content_digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
        if expected_digest is not None and content_digest!=expected_digest:
            raise RouterError("File changed since it was evaluated or read; restart reading or reroute")
        if offset>len(text): raise RouterError("Offset is beyond the end of the file")
        end=min(len(text),offset+limit)
        return {"skill_id":skill.id,"name":skill.name,"path":path,"content":text[offset:end],"content_digest":content_digest,"offset":offset,"next_offset":end if end<len(text) else None,"total_chars":len(text),"base_directory":str(skill.directory)}
