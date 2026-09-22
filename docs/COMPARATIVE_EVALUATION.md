# Reproducible routing comparison

The comparison suite measures **skill selection**. It does not establish that Jev improves a main model's final task success, latency or total bill. The default run uses no API and reads no credentials.

## Authored challenge dataset

[`examples/comparison/manifest.json`](../examples/comparison/manifest.json) records the provenance and labeling rule. The suite has 96 original project-authored cases, 48 English and 48 Korean, over 16 narrow illustrative skills:

| Category | Cases | What it checks |
| --- | ---: | --- |
| Direct requests | 32 | Explicitly named capabilities |
| Paraphrases | 32 | Indirect descriptions of the intended work |
| Near misses | 12 | Correctness vs performance, inspect vs transform, translate vs write, and similar neighbors |
| No matching skill | 12 | Unrelated requests, including misleading shared words |
| Multiple required skills | 8 | Exact selection of two distinct capabilities |

The tasks and labels were authored for this project before running the baselines. They are **not independently held out, human-adjudicated, or sampled from production traffic**. English/Korean pairs and prompt families are correlated. A high score on this suite cannot establish broad real-world quality.

The existing 24-case starter fixture remains available for backward-compatible smoke tests. The new challenge suite does not alter it.

## Free local comparison

From an installed repository checkout:

```sh
python scripts/compare_routing.py --out jev-local-results/comparison.json
```

Two independent metadata-only BM25 baselines run against the same skills and tasks. Their implementation is separate from the router's production retrieval index and sees no expected labels during selection:

- `bm25-top1`: choose the highest positive-scoring skill, or no skill if every score is zero.
- `bm25-threshold`: choose up to `max_skills`, requiring score ≥ 4, at least 72% of the top score, and at least two matched terms.

Both use fixed Okapi parameters `k1=1.2`, `b=0.75`, Unicode-normalized words and Hangul bigrams. These constants were not fitted to the authored labels. Top-1 cannot solve a two-skill case exactly; the threshold baseline can. Do not use the weaker baseline alone to claim superiority.

Reports include exact-set accuracy, partial precision/recall when selected sets are available, language/category breakdowns, false selections on no-match cases, abstentions, errors, attempted/unattempted counts, and paired case comparisons. Errors are wrong in the attempted-case denominator. Unattempted cases remain visible.

Baseline latency measures metadata scoring; Jev latency includes catalog checks, network activity and selected-content reads. The difference is **not measured end-to-end time saved**.

The recorded local run is available in [`comparison-report.json`](comparison-report.json):

| Method | Exact set matches | English | Korean | False selections on 12 no-match cases |
| --- | ---: | ---: | ---: | ---: |
| BM25 top-1 | 60/96 (62.5%) | 27/48 | 33/48 | 8 |
| BM25 threshold | 53/96 (55.2%) | 22/48 | 31/48 | 3 |
| Live Jev | Not measured | Not measured | Not measured | Not measured |

These figures describe fixed lexical baselines on this authored suite. They establish neither a Jev advantage nor a disadvantage. There is no paid-model result or measured total-cost saving in this report.

## Production candidate retention

The same report also measures the production metadata index independently of Jev: at limit 8 it retains 83/92 required skills (90.22%) and every required skill in 75/84 positive cases. This is candidate recall, not selection accuracy. Nine positive cases lose a required candidate. No-match cases do not enter this recall denominator. `--candidate-limit` defaults to **8 in this comparison script**, so narrowing is exercised with the 16-skill suite; the production default remains **64**. Set it explicitly for your workload. [Scaling details](SCALING.md).

## Optional live Jev comparison

The default example configuration permits three selected skills, enough for the two-skill cases. The API key is read only after explicit live opt-in and all dataset/report validation. Tasks, metadata and shortlisted instruction excerpts are then sent to TypeSafe.

```sh
# One strategy. The cap includes retries across the entire run.
python scripts/compare_routing.py --allow-live --max-requests 256 \
  --out jev-local-results/jev-all.json

# Compare full-catalog and opt-in local candidate retrieval.
# Both share one global cap; it is not a fresh cap for each strategy.
python scripts/compare_routing.py --allow-live --strategy both --max-requests 512 \
  --out jev-local-results/jev-all-vs-indexed.json

# Explicit safety switch: still free, even with --allow-live.
python scripts/compare_routing.py --allow-live --preflight
```

These are transport-attempt limits, **not dollar limits**. Calls can fail or consume the cap before all cases finish. The evaluator records partial results, stops after a provider/budget failure, and returns a nonzero status when the live run is incomplete. Two strategies run sequentially, so temporal provider variation remains a confounder.

Live reports, including partial results, are saved under ignored `jev-local-results/` when `--out` is omitted. Stdout contains a concise version without per-case records.

`--config PATH` accepts a real local catalog; expected names in the dataset must exist there, and `max_skills` must accommodate the largest expected set. `--rates PATH` accepts the existing exact-model rate format documented for `evaluate_live.py`; no price is guessed. Missing usage remains unknown. An estimate is never a verified invoice or a combined host-model bill.

Previously generated `evaluate_live.py` schema-3 reports can be paired with the local baselines:

```sh
python scripts/compare_routing.py --jev-report jev-local-results/live.json \
  --out jev-local-results/imported-comparison.json
```

The task and catalog content fingerprints must match. Imported scores are labeled producer-reported; identity checks do not prove provider authenticity or independently re-score raw selections. Reports omit task text, skill bodies, local directories and credentials.

## Actual host task trials

A fair native-versus-routed trial needs the same main model, system instructions, tool access, task inputs and success rubric. Use independent fresh workspaces, repeat tasks in randomized order, retain the tool traces privately, and score final artifacts against task-specific acceptance checks. Measure the entire task, including retries, Jev requests and main-model usage. A skill selection alone is not task success.

This repository does not claim those host trials happened. It can import caller-scored results without turning them into verified evidence:

```sh
python scripts/compare_routing.py --host-results jev-local-results/host-results.json \
  --out jev-local-results/with-host-results.json
```

Input schema (copy the actual fingerprints from the local comparison report):

```json
{
  "schema_version": 1,
  "dataset_sha256": "COPY_FROM_COMPARISON_REPORT",
  "catalog_content_sha256": "COPY_FROM_COMPARISON_REPORT",
  "records": [
    {"case": 0, "strategy": "native", "task_success": true, "seconds": 42.0,
     "input_tokens": 1200, "output_tokens": 400, "reported_cost_usd": null},
    {"case": 0, "strategy": "routed", "task_success": true, "seconds": 39.0,
     "input_tokens": 900, "output_tokens": 410, "reported_cost_usd": null}
  ]
}
```

Those example numbers illustrate the schema and are **not measured results**. `case` is the zero-based dataset row index. Each strategy/case pair must be unique. Only matching native/routed pairs contribute to comparison; excluded records are counted. Missing cost/token fields remain unknown, and totals are withheld when any paired observation is missing. Imported results remain explicitly caller-supplied and caller-scored.

## Official MCP client smoke test

The optional verification dependency is the official [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk). The test uses its `ClientSession` and `stdio_client` APIs against a real `python -m jev_skill_router ... serve` subprocess, following the SDK's [stdio client example](https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/clients/stdio_client.py).

```sh
python -m pip install '.[protocol]'
python scripts/check_mcp_client.py --out jev-local-results/mcp-sdk.json
```

It creates and removes a temporary offline profile, then checks initialization, tool discovery, routing, digest-protected UTF-8 pagination, traversal rejection, error recovery, ping, and decision-cache reuse. It uses no API credentials and makes no provider calls. Missing SDK is a nonzero “not performed” result, not a pass.

This proves **official SDK ↔ actual stdio server interoperability**. It does not prove that Codex, Claude Code or Cursor desktop discovery/instruction use succeeds, nor that live Jev selection is accurate. Run the separate host verification workflow for available actual hosts.

The SDK run for this version is recorded in [mcp-sdk-report.json](mcp-sdk-report.json). Separate actual Codex/Claude CLI connection checks are in [host-connection-report.json](host-connection-report.json); they do not establish model task success.
