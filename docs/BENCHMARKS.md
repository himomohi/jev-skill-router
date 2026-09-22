# Context accounting, without inflated claims

## The committed benchmark

Run `python scripts/benchmark_context.py`. It writes [benchmark.json](benchmark.json) and prints the same deterministic numbers. It calls no model. The bytes include JSON punctuation and escaping as produced by the implementation's compact UTF-8 serializer.

The inventory is synthetic: names `workflow-0000` onward, 236-character descriptions, and one 2,144-character selected instruction body. Using repeated text makes the artifact deterministic; it does not model routing difficulty or natural-language diversity. Hashes of both serialized sides are stored in the JSON report.

Baseline = all name/description metadata + one selected instruction payload.

Router = one MCP tool schema + one bootstrap + one representative route invocation + representative result bookkeeping + the same selected instruction payload.

This is **not** an eager-load-all-bodies baseline. Existing skill-reader tool definitions are excluded from the baseline, while the new router tool definition is included on the router side. Additional loaded bridge text, host-specific envelopes, or duplicate bootstrap placement can increase a real integration's overhead.

The table represents one skill-related context after selection, not cumulative input/output across all model calls. A real MCP workflow may need an extra main-model call to invoke the router, whereas a custom harness or pre-turn hook can route before the first main-model request.

## Why bytes, not tokens?

The target main-model tokenizer was not specified, and a tokenizer package could not be downloaded in the build environment. Consequently the committed evidence reports **exact UTF-8 bytes only**. Byte reduction is not automatically token reduction, particularly with mixed Korean/English text.

For a tokenizer-specific estimate, install the optional `tokens` extra and run:

```bash
python -m pip install '.[tokens]'
python scripts/benchmark_context.py --encoding cl100k_base --out local-token-benchmark.json
```

That encoding is only an example, not a claim about the currently deployed model. Provider billing or a model's own token counter is the appropriate source for actual charged tokens. A tiktoken encoding may require an initial vocabulary download.

Use `jev-skills benchmark --skill NAME` for your actual library. Its selected-skill path uses a smaller illustrative accounting envelope, explicitly identified in the output. It is a local what-if calculation, not a live response capture; do not mix its numbers with the committed synthetic table as though they used identical content.

## Total-context and cost accounting

Let B be the original skill-related payload, R the routed skill-related payload, and F all unchanged conversation/host context. Skill-payload reduction is `(B-R)/B`; total-context reduction is `(B-R)/(F+B)`. The second is smaller whenever F is positive.

Actual total cost must include:

- Main model input, including any cached/uncached distinctions and any added tool round trip.
- Jev's input tokens for **every** ranking/verification request and retries.
- Extra reference pages, execution tool responses, and later turns carrying earlier content.

Routing is not free and does not erase instructions already present in the conversation. A long-running MCP process caches exact repeated requests for up to 180 seconds by default, keyed on task, supplied context, config and catalog content hashes. Separate CLI/hook processes have separate caches. Repeated new tasks still need routing.

## Latency, quality and live evaluation

No live model latency, cost, authentication, or semantic accuracy was measured. `api_calls` counts logical successful-path attempts to `ask`; HTTP retries can create additional provider requests. `routing_seconds` measures a noncached route's local elapsed selection time; cached results retain the original value and mark `cache_hit=true`, so it is not the cache-hit latency.

`evaluate_live.py` measures request wall-clock time, exact selected-name match, errors, resolved model versions and reported usage. Its labels need human review. Its six starter cases are not a representative benchmark. It does not evaluate whether the final host completed the user's task successfully.

For a reliable comparison, evaluate metadata-only native routing, this router, and a manually supplied correct skill across the same realistic EN/KO tasks. Include no-match, ambiguous, multi-skill, long-body and unavailable-dependency cases. Record every error and abstention rather than dropping them. Separate cold/warm sessions and compare full task success, total billed usage and end-to-end wall time.
