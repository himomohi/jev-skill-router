from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

class RouterError(Exception):
    """Safe, user-facing error. Never include API response bodies or secrets."""

def home_dir() -> Path:
    return Path(os.environ.get("JEV_SKILLS_HOME", "~/.jev-skill-router")).expanduser().resolve()

def config_path() -> Path:
    return home_dir() / "config.json"

def atomic_json(path: Path, value: object) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".jev-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

@dataclass
class Config:
    roots: list[str] = field(default_factory=list)
    model: str = "jev-latest"
    mode: str = "live"
    max_skills: int = 1
    shortlist: int = 3
    min_fit: float = 0.65
    min_confidence: float = 0.50
    excerpt_chars: int = 900
    max_output_chars: int = 12000
    max_request_bytes: int = 24000
    max_api_calls: int = 32
    max_concurrency: int = 3
    max_catalog_skills: int = 4096
    timeout_seconds: float = 15.0
    route_timeout_seconds: float = 45.0
    retries: int = 2
    cache_seconds: int = 180
    candidate_strategy: str = "all"
    candidate_limit: int = 64
    def validate(self) -> Config:
        if not isinstance(self.mode, str) or self.mode not in {"live", "offline"}:
            raise RouterError("mode must be live or offline")
        if not isinstance(self.roots, list) or any(not isinstance(x, str) for x in self.roots):
            raise RouterError("roots must be a list of local paths")
        if not isinstance(self.candidate_strategy,str) or self.candidate_strategy not in {'all','indexed'}:
            raise RouterError("candidate_strategy must be all or indexed")
        for key, lo, hi in [
            ("max_skills",1,3),("shortlist",1,8),("excerpt_chars",100,2000),
            ("max_output_chars",1000,50000),("max_request_bytes",8000,24000),
            ("max_api_calls",2,64),("max_concurrency",1,8),("max_catalog_skills",1,10000),
            ("retries",0,3),("cache_seconds",0,600),
            ("candidate_limit",8,512),
        ]:
            value = getattr(self,key)
            if type(value) is not int or not lo <= value <= hi:
                raise RouterError(f"{key} must be an integer from {lo} to {hi}")
        for key,lo,hi in [("min_fit",0.0,1.0),("min_confidence",0.0,1.0),("timeout_seconds",1.0,60.0),("route_timeout_seconds",1.0,180.0)]:
            value=getattr(self,key)
            if type(value) not in (int,float) or not lo <= value <= hi:
                raise RouterError(f"{key} is outside the supported range")
        if not isinstance(self.model,str) or not self.model or len(self.model)>100:
            raise RouterError("model must be a nonempty model ID")
        return self
    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        if not path.is_file():
            raise RouterError(f"No configuration at {path}. Run jev-skills setup first.")
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data,dict): raise ValueError()
            return cls(**data).validate()
        except (ValueError, TypeError, OSError) as e:
            raise RouterError("Invalid configuration. Use a JSON object with documented fields.") from e
    def save(self, path: Path | None = None) -> None:
        self.validate()
        atomic_json(path or config_path(), asdict(self))

def api_key() -> str:
    value=os.environ.get("TYPESAFE_API_KEY", "").strip()
    if value:
        if "\n" in value or "\r" in value:
            raise RouterError("Invalid API key format")
        return value
    try:
        import keyring
        backend=keyring.get_keyring()
        module=type(backend).__module__
        if not module.startswith(("keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService")):
            raise RouterError("No supported OS keychain. Set TYPESAFE_API_KEY in the server environment.")
        value=keyring.get_password("jev-skill-router", "typesafe-api-key")
        if value: return value
    except ImportError:
        pass
    except RouterError:
        raise
    except Exception as e:
        raise RouterError("OS keychain unavailable. Unlock it or use TYPESAFE_API_KEY.") from e
    raise RouterError("No Jev key. Run jev-skills auth or set TYPESAFE_API_KEY. No automatic offline fallback.")
