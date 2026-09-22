from __future__ import annotations
import json
import math
import time
from email.utils import parsedate_to_datetime
from datetime import datetime,timezone
from typing import Callable
import httpx
from .config import Config, RouterError

ENDPOINT='https://api.typesafe.ai/v1/systemone'
RETRY_STATUSES={429,500,502,503,504,529}

def encoded(value: object) -> bytes:
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')

def probability(value: object) -> float:
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:
        raise RouterError("Invalid probability in Jev response")
    return float(value)

def validate_response(data: object, questions: dict) -> dict:
    if not isinstance(data,dict) or not isinstance(data.get('answers'),dict) or not isinstance(data.get('model'),str):
        raise RouterError("Malformed Jev response")
    for key,q in questions.items():
        answer=data['answers'].get(key)
        if not isinstance(answer,dict) or answer.get('type')!=q['type']:
            raise RouterError("Jev answer is missing or has the wrong type")
        if q['type']=='noul':
            probability(answer.get('noul'));continue
        probability(answer.get('confidence'))
        expected=set(q['criteria']) if q['type']=='choice' else {str(i) for i in range(len(q['criteria']))}
        probabilities=answer.get('probabilities')
        if not isinstance(probabilities,dict) or set(probabilities)!=expected:
            raise RouterError("Jev returned unknown or missing probability IDs")
        if abs(sum(probability(v) for v in probabilities.values())-1)>0.025:
            raise RouterError("Invalid Jev probability distribution")
        if q['type']=='choice':
            selected=answer.get('choice')
            if selected not in expected or probabilities[selected]+1e-6<max(probabilities.values()):
                raise RouterError("Invalid Jev choice")
        else:
            score=answer.get('score')
            if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=len(q['criteria'])-1:
                raise RouterError("Invalid Jev score")
    return data

class JevClient:
    """One persistent connection pool. Strict documented REST schema, no chat API."""
    def __init__(self,config:Config,key:str,transport:httpx.BaseTransport|None=None,sleep:Callable=time.sleep):
        self.config=config;self.sleep=sleep
        self.http=httpx.Client(headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},timeout=config.timeout_seconds,follow_redirects=False,transport=transport)
    def close(self): self.http.close()
    def ask(self,state:dict,questions:dict)->dict:
        payload=encoded({'model':self.config.model,'state':state,'questions':questions})
        if len(payload)>self.config.max_request_bytes:
            raise RouterError("Jev request exceeds the configured UTF-8 byte budget")
        for attempt in range(self.config.retries+1):
            try:
                response=self.http.post(ENDPOINT,content=payload)
            except httpx.RequestError as e:
                # Do not silently retry ambiguous network failures: a prior request may have been billed.
                raise RouterError("Jev connection failed or timed out; no skill was loaded") from e
            if response.status_code in RETRY_STATUSES and attempt<self.config.retries:
                delay=min(8.0,0.5*(2**attempt))
                retry_after=response.headers.get('retry-after')
                if retry_after:
                    try: requested=float(retry_after)
                    except ValueError:
                        try: requested=(parsedate_to_datetime(retry_after)-datetime.now(timezone.utc)).total_seconds()
                        except (ValueError,TypeError,OverflowError): requested=delay
                    if requested>8:
                        raise RouterError("Jev asks for a longer retry delay; retry the task later")
                    if math.isfinite(requested): delay=max(delay,requested,0)
                self.sleep(delay);continue
            if not response.is_success:
                raise RouterError(f"Jev HTTP {response.status_code}; check authentication, limits, and model configuration")
            if len(response.content)>2_000_000:
                raise RouterError("Jev response exceeds the size limit")
            try: data=response.json()
            except ValueError as e: raise RouterError("Jev returned invalid JSON") from e
            return validate_response(data,questions)
        raise RouterError("Jev retry budget exhausted")
