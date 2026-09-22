"""Local UTF-8 content accounting; deliberately not a model-token estimator."""
from __future__ import annotations
from .catalog import Catalog
from .config import Config, RouterError
from .jev import encoded
from .mcp import BOOTSTRAP, TOOL


def measure(config: Config, skill_name: str | None = None) -> dict:
    catalog = Catalog(config.roots, config.max_catalog_skills)
    if not catalog.skills:
        raise RouterError('No skills to measure')
    roster = [{'name':s.name, 'description':s.description} for s in catalog.skills.values()]
    baseline = encoded({'available_skills':roster})
    discovery = encoded({'instructions':BOOTSTRAP, 'tools':[TOOL]})
    result = {
        'unit':'UTF-8 bytes, not model tokens', 'catalog_size':len(roster),
        'metadata_bytes':len(baseline), 'router_discovery_bytes':len(discovery),
        'discovery_reduction_percent':round(100*(1-len(discovery)/len(baseline)),2),
        'model_calls':0, 'warnings':catalog.warnings,
        'scope':'Skill-related serialized content only. Excludes host framing, conversation, Jev requests, billing and latency.',
    }
    if skill_name:
        matches = [s for s in catalog.skills.values() if skill_name in {s.name,s.id}]
        if len(matches)!=1:
            raise RouterError('Select one unique skill name or ID from jev-skills list')
        payload = encoded({'selected':[catalog.read(matches[0].id,limit=config.max_output_chars)]})
        # Explicit fixed accounting envelope. It is not a recorded inference response.
        overhead = encoded({'tool':'skill_router','arguments':{'action':'route','task':'<focused task>'},
            'status':'selected','provider':'jev','api_calls':None,'usage':None,
            'catalog_fingerprint':catalog.fingerprint,'note':'illustrative route bookkeeping'})
        before=len(baseline)+len(payload);after=len(discovery)+len(overhead)+len(payload)
        result.update(selected_skill=matches[0].name,selected_payload_bytes=len(payload),
            baseline_with_selected_bytes=before,router_with_selected_bytes=after,
            one_context_reduction_percent=round(100*(1-after/before),2),
            bookkeeping='Illustrative fixed envelope; real route fields, prompt length and host overhead can differ.')
    return result
