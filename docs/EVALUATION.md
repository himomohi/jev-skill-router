# Measuring real routing behavior

The live evaluator measures Jev selection accuracy, additional routing latency, HTTP attempts and reported usage. It does not execute the selected skill or the host's main model. A smaller context envelope is not evidence of lower total cost or faster task completion.

## Start without an API call

From the repository root after installation:

```bash
python scripts/evaluate_live.py --preflight
```

This validates the bundled six example skills and 24 authored cases: 12 English, 12 Korean, including six requests that should select no skill. No credential is read and no HTTP client is constructed. Omitting `--allow-live` also selects this safe preflight mode. `--preflight` takes precedence if both flags are present.

To use your own local catalog and JSONL dataset:

```bash
python scripts/evaluate_live.py my-cases.jsonl --config local-config.json --preflight
```

Each case uses unique catalog skill names as expected selections:

```json
{"language":"ko","task":"SQL 조인으로 합계가 중복되는지 검토해줘.","expected":["sql-review"]}
{"language":"en","task":"Suggest three names for a kitten.","expected":[]}
```

Optional `context` is text. Languages are `en`, `ko`, or `other`; old cases without this field use Hangul detection. A run accepts 1–200 cases and rejects missing expected skills, duplicate skill names, invalid catalog entries and oversized task/context inputs before accessing credentials.

The included cases are starter checks, not a held-out representative benchmark. Extend them with independently labeled, non-sensitive tasks, near misses, multi-skill tasks where enabled, and long skills before drawing conclusions about your workload.

## Run explicitly

Configure the TypeSafe key through `jev-skills auth` on a supported OS keychain, or supply `TYPESAFE_API_KEY` in the process environment. The evaluator does not automatically load `.env` files.

```bash
python scripts/evaluate_live.py --allow-live --max-requests 64
```

The flag authorizes billed TypeSafe calls and transmission of task/context, skill metadata and candidate excerpts. The global request cap counts **every HTTP attempt, including retries**. An authentication, provider, deadline or budget error stops the run and preserves results collected so far. The bundled default disables retries; a supplied configuration controls retries, per-route deadlines and concurrency.

An interrupted case retains its elapsed time and HTTP counts as an error. Cold-case completion and warm-cache verification are reported separately. Exit code 0 means the full evaluation and immediate cache checks completed, not that every selection was correct. Incomplete runs or failed warm checks return 1; input/setup errors return 2.

The default report goes into an ignored `jev-local-results/` directory. Use `--out result.json` for a chosen location. No tasks, contexts, skill names/bodies, local paths or keys are written to the report. Numeric case indices refer to zero-based JSONL order; hashes identify the dataset and catalog content. Keep a private copy of your input cases if you need to interpret failures later.

## Read the report

| Measurement | Meaning |
|---|---|
| Exact-match accuracy including errors | Correct selection sets divided by attempted cases; errors count as incorrect |
| Completed-only accuracy | Correct selection sets divided by cases that returned a routing result |
| Planned / attempted / unattempted | Shows incomplete coverage after an early stop; results are not generalized to skipped cases |
| English / Korean breakdown | Separate accuracy and error counts, including languages not reached before a stop |
| No-match false selections | Irrelevant tasks that still loaded a skill |
| Required-skill abstentions | Relevant tasks returning `no_match` or `uncertain`; API errors are counted separately |
| Cold latency | Wall-clock duration of `Router.route` only, with the decision cache cleared before every case, including duplicate tasks |
| Warm latency | The same `Router.route`-only scope for an immediate exact repeat, with cache-hit, same-selection and HTTP counts recorded |
| HTTP / retry requests | Transport attempts, including failed calls and retries; logical `api_calls` is reported separately |
| Usage completeness | False if any attempted request lacks valid usage; unknown usage is not zero cost |
| Context bytes | Actual router serialization versus a modeled native metadata inventory with the same selected content |

Cold cases share a persistent HTTP pool, and the operating system may cache files. They do not measure cold process startup or a fresh TLS connection on every case. Warm repeats deliberately use a 600-second decision-cache TTL, regardless of the input configuration; that effective configuration is recorded. Warm results do not predict the performance of a different request or a new process.

Report schema **3** times only the routing call for both cold and warm attempts, including failed or interrupted calls. Catalog checks, provider work and selected-content reads inside the router are included; evaluator result classification, context-byte calculation, metrics snapshots and report serialization are excluded. `warm_all_attempts` includes failed repeats, `warm_errors` counts them, and `warm_cache` includes only successful cache-hit repeats.

All latency distributions include sample counts. The completed-only distribution excludes failed calls; the all-attempts distribution includes them. Positive context-byte reduction means less skill-related content; negative means the router adds content. Neither includes real main-model token framing, cached-token billing, or a complete conversation.

### Optional pricing

No built-in price is assumed. `billed_cost_usd` remains unknown because the evaluator does not inspect an invoice. To estimate Jev cost, provide explicit rates for the **exact returned model ID**, not an alias:

```json
{"model":"exact-returned-model-id","input_usd_per_million":1.0,"output_usd_per_million":2.0}
```

These numbers are illustrative, not current TypeSafe prices. Save your verified rates locally, then add `--rates rates.json`. An estimate is produced only for a complete run with complete usage and that exact observed model. Retries or failures with unreported usage leave the total estimate unknown. Host-model cost remains unmeasured.

### Compare two routing runs

```bash
python scripts/evaluate_live.py --allow-live --config serial.json --out serial-result.json
python scripts/evaluate_live.py --allow-live --config parallel.json --compare-report serial-result.json --out parallel-result.json
```

For example, set `max_concurrency` to 1 versus 3 while keeping other settings constant. The comparison requires schema 3 reports with the same dataset and catalog content; it permits configuration changes and reports them alongside observed model IDs. Only shared case indices are paired. Repeated runs still face service/load and connection variability, so one latency difference is not proof of an improvement. A model alias may resolve to a different version between runs.

Schema 2 reports included evaluator accounting in cold latency but not warm latency. They are rejected before credential lookup or paid requests; collect a new baseline instead of relabeling an old report as schema 3.

This is a comparison of recorded routing runs. It does not benchmark native Codex/Claude/Cursor skill selection. To establish overall efficiency, separately run the same held-out tasks in a host with native discovery and with routing, confirm the original skill inventory is hidden in the routed condition, grade final outputs against the same rubric, and record **all** provider/main-model usage and wall-clock task duration. Keep model versions, tools and approval conditions comparable. The report leaves final-task success, total cost and total completion time explicitly unknown until that experiment is performed.
