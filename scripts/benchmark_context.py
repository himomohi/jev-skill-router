"""Deterministic serialized-content accounting. No LLM calls or quality claims.

The same selected instruction payload appears on both sides. Baseline assumes
progressive disclosure, not every SKILL.md eagerly loaded. UTF-8 bytes are exact;
model tokens and prices are deliberately not inferred from byte counts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jev_skill_router.mcp import BOOTSTRAP,TOOL
from jev_skill_router.jev import encoded
from jev_skill_router.router import READ_INSTRUCTION

DESCRIPTION=(
    'Apply a documented specialist workflow to the named task. Inspect relevant inputs, '
    'respect environment constraints, validate outputs with focused checks, and report '
    'remaining uncertainty. Use only when the request needs this capability.'
)
BODY=(
    '# Selected specialist workflow\n\n'
    'Inspect the user request and the relevant local inputs before taking action. '
    'Preserve existing behavior outside the requested change. Record assumptions, '
    'perform the smallest meaningful validation, and report what was actually tested.\n\n'
)*8
TASK='Apply the specialist workflow to the current input and verify the result.'

def scenario(count:int,tokenizer=None)->dict:
    roster=[{'name':f'workflow-{i:04d}','description':DESCRIPTION} for i in range(count)]
    # One logical main-model request after skill selection, not a whole multi-turn bill.
    selected={'skill_id':'s_0123456789abcdef','name':'workflow-0000','path':'SKILL.md',
              'content':BODY,'content_digest':hashlib.sha256(BODY.encode()).hexdigest(),
              'offset':0,'next_offset':None,'total_chars':len(BODY),
              'base_directory':'/user/external-skills/workflow-0000'}
    baseline_discovery=encoded({'available_skills':roster})
    router_discovery=encoded({'instructions':BOOTSTRAP,'tools':[TOOL]})
    common=encoded({'selected':[selected]})
    request_overhead=encoded({'tool':'skill_router','arguments':{'action':'route','task':TASK}})
    # Fixed sample route bookkeeping, not live measured timing or model output.
    route_overhead=encoded({'status':'selected','provider':'jev','models':['jev-latest'],
        'api_calls':2,'http_requests':2,'retry_requests':0,'usage':None,'shortlisted':3,'catalog_size':count,'cache_hit':False,
        'routing_seconds':None,'elapsed_seconds':None,'catalog_fingerprint':'0'*64,'warnings':[],
        'instruction':READ_INSTRUCTION,'retrieval':{'strategy':'all','considered_skills':count,'index_applied':False,'truncated':False}})
    baseline=baseline_discovery+common
    routed=router_discovery+request_overhead+route_overhead+common
    def drop(a,b):return round(100*(1-b/a),2)
    result={'skills':count,'metadata_bytes':len(baseline_discovery),'router_discovery_bytes':len(router_discovery),
            'selected_payload_bytes':len(common),'route_request_and_bookkeeping_bytes':len(request_overhead)+len(route_overhead),
            'progressive_baseline_bytes':len(baseline),'routed_main_bytes':len(routed),
            'discovery_reduction_percent':drop(len(baseline_discovery),len(router_discovery)),
            'one_context_reduction_percent':drop(len(baseline),len(routed)),
            'baseline_sha256':hashlib.sha256(baseline).hexdigest(),'routed_sha256':hashlib.sha256(routed).hexdigest()}
    if tokenizer:
        a=len(tokenizer.encode(baseline.decode(),disallowed_special=()));b=len(tokenizer.encode(routed.decode(),disallowed_special=()))
        result['optional_tokenizer']={'encoding':tokenizer.name,'baseline_tokens':a,'routed_tokens':b,'reduction_percent':drop(a,b)}
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'docs/benchmark.json')
    parser.add_argument('--encoding',help='Optional tiktoken encoding, not necessarily the deployed model tokenizer')
    args=parser.parse_args();tokenizer=None
    if args.encoding:
        import tiktoken
        tokenizer=tiktoken.get_encoding(args.encoding)
    report={'method':'synthetic serialized content, one main-model context after one skill is loaded',
            'unit':'UTF-8 bytes, not model tokens','calls_to_any_model':0,
            'description_characters':len(DESCRIPTION),'selected_instruction_characters':len(BODY),
            'assumptions':['Same selected skill payload on both sides.','Baseline loads metadata, not all skill bodies.',
                'Router side includes static MCP schema, bootstrap, a call and bookkeeping.',
                'Generic host prompts and token framing excluded from both. Existing baseline tool schema excluded, conservatively.',
                'Jev inputs and network latency excluded: separate service, not zero cost.',
                'No claim about routing accuracy, token savings, cached pricing, or end-to-end speed.'],
            'results':[scenario(n,tokenizer) for n in [5,50,200,500]]}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
