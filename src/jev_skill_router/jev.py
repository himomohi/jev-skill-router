from __future__ import annotations
import asyncio
import inspect
import json
import math
import time
from dataclasses import dataclass
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

@dataclass
class RequestBudget:
    """Shared deadline and actual HTTP-attempt allowance for one route."""
    limit: int
    deadline: float
    used: int = 0

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RouterError("Overall routing deadline exceeded; no skill was loaded")
        return remaining

    def reserve(self) -> None:
        self.remaining()
        if self.used >= self.limit:
            raise RouterError("Per-route HTTP request budget exhausted; retries count toward the limit")
        self.used += 1


class JevClient:
    """Synchronous facade over a persistent, cancellable asynchronous HTTP pool.

    Use one client from one calling thread. In an async host, call the synchronous
    router using asyncio.to_thread instead of nesting an event loop.
    """
    def __init__(self,config:Config,key:str,transport:httpx.AsyncBaseTransport|None=None,sleep:Callable=time.sleep,*,max_requests:int|None=None):
        if max_requests is not None and (type(max_requests) is not int or max_requests < 1):
            raise RouterError("max_requests must be a positive integer")
        self.config=config;self.sleep=sleep;self.max_requests=max_requests
        self.runner=asyncio.Runner()
        self.http=httpx.AsyncClient(headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},timeout=config.timeout_seconds,follow_redirects=False,transport=transport)
        self._metrics={key:0 for key in ('api_calls','http_requests','retry_requests','request_bytes','input_tokens','output_tokens','unreported_requests')}
        self._closed=False

    def _run(self, coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self.runner.run(coroutine)
        coroutine.close()
        raise RouterError("Use asyncio.to_thread for the synchronous router inside an async host")

    def close(self):
        if not self._closed:
            self._run(self.http.aclose())
            self.runner.close()
            self._closed=True

    def metrics_snapshot(self) -> dict:
        return dict(self._metrics)

    def ask(self,state:dict,questions:dict,*,budget:RequestBudget|None=None)->dict:
        budget=budget or RequestBudget(self.config.max_api_calls,time.monotonic()+self.config.route_timeout_seconds)
        return self._run(self._ask(state,questions,budget))

    def ask_many(self,state:dict,batches:list[dict],*,budget:RequestBudget)->list[dict]:
        return self._run(self._ask_many(state,batches,budget))

    async def _ask_many(self,state,batches,budget):
        semaphore=asyncio.Semaphore(self.config.max_concurrency)
        failed=False
        async def ask_one(questions):
            nonlocal failed
            async with semaphore:
                if failed: raise asyncio.CancelledError()
                budget.remaining()
                try:
                    return await self._ask(state,questions,budget)
                except BaseException:
                    failed=True
                    raise
        tasks=[asyncio.create_task(ask_one(questions)) for questions in batches]
        try:
            async with asyncio.timeout(budget.remaining()):
                # gather preserves catalog order even when requests finish out of order.
                return await asyncio.gather(*tasks)
        except TimeoutError as e:
            raise RouterError("Overall routing deadline exceeded; no skill was loaded") from e
        finally:
            # Do not let paid requests continue in the background after returning.
            for task in tasks:
                if not task.done(): task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

    async def _pause(self,delay):
        if self.sleep is time.sleep:
            await asyncio.sleep(delay)
        else:
            result=self.sleep(delay)
            if inspect.isawaitable(result): await result

    async def _ask(self,state:dict,questions:dict,budget:RequestBudget)->dict:
        payload=encoded({'model':self.config.model,'state':state,'questions':questions})
        if len(payload)>self.config.max_request_bytes:
            raise RouterError("Jev request exceeds the configured UTF-8 byte budget")
        self._metrics['api_calls']+=1
        for attempt in range(self.config.retries+1):
            budget.remaining()
            if self.max_requests is not None and self._metrics['http_requests']>=self.max_requests:
                raise RouterError("Evaluation HTTP request budget exhausted; no further request sent")
            budget.reserve()
            self._metrics['http_requests']+=1
            self._metrics['retry_requests']+=int(attempt>0)
            self._metrics['request_bytes']+=len(payload)
            self._metrics['unreported_requests']+=1
            try:
                async with asyncio.timeout(min(self.config.timeout_seconds,budget.remaining())):
                    async with self.http.stream('POST',ENDPOINT,content=payload) as response:
                        content=bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content)+len(chunk)>2_000_000:
                                raise RouterError("Jev response exceeds the size limit")
                            content.extend(chunk)
            except TimeoutError as e:
                message="Overall routing deadline exceeded" if time.monotonic()>=budget.deadline else "Jev request timed out"
                raise RouterError(message+"; no skill was loaded") from e
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
                if delay>=budget.remaining():
                    raise RouterError("Retry delay exceeds the remaining routing deadline")
                await self._pause(delay);continue
            if not response.is_success:
                raise RouterError(f"Jev HTTP {response.status_code}; check authentication, limits, and model configuration")
            try: data=json.loads(content)
            except ValueError as e: raise RouterError("Jev returned invalid JSON") from e
            validated=validate_response(data,questions)
            usage=validated.get('usage')
            if isinstance(usage,dict) and all(type(usage.get(key)) is int and usage[key]>=0 for key in ('input_tokens','output_tokens')):
                self._metrics['input_tokens']+=usage['input_tokens']
                self._metrics['output_tokens']+=usage['output_tokens']
                self._metrics['unreported_requests']-=1
            return validated
        raise RouterError("Jev retry budget exhausted")
