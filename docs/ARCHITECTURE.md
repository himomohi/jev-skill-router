# Architecture

## Control flow

`Config → Catalog → Router → JevClient → validated decision → bounded Catalog.read → MCP/CLI/hook`.

`Catalog` recursively scans trusted roots. It parses YAML with `safe_load`, retains full descriptions, and gives each absolute skill path a stable hash ID. Duplicate human-readable names do not alias one another. File-content hashes create the catalog fingerprint. Linux/macOS reuse parsed files whose device/inode, mode, size, modification time and change time are unchanged; directory discovery and path checks still run. Ordinary same-size edits with restored modification times are detected through change time. Windows conservatively rereads files because `stat` change time can represent creation time. `Catalog.refresh(force=True)` bypasses reuse on filesystems with unreliable metadata. Neither mode is a hostile-filesystem sandbox.

`Router` sends focused task/context as state. Metadata lives in Choice criteria rather than the main LLM prompt. Large inventories are packed into bounded Choice requests. Every shard contributes up to three candidates. Each shortlisted skill is then assessed by two independent questions; both include the same description and excerpt because questions do not see one another's question data.

Long-body evidence includes the opening, ending and two interior windows within the same `excerpt_chars` limit (900 by default). Literal task-term overlap prioritizes interior windows; without overlap, both interior thirds are sampled. This heuristic selects evidence only: Jev still chooses and verifies skills. It is not a guarantee of complete coverage, semantic quality, or cross-language understanding. Full short bodies are preserved and truncated excerpts are explicitly marked.

Noul fit >= 0.65, Score usefulness >= 1.5 on a 0–2 rubric, and Score confidence >= 0.50 are the defaults. These are starting policies, **not calibrated thresholds**. Accepted candidates are sorted by fit, score, confidence, then ID. Scores from the same absolute rubric are used across shards; shard-local Choice probabilities are not compared globally. Default `max_skills=1` can be changed to 2 or 3.

If candidates fail the fit/usefulness gates, return `no_match`. A useful but low-confidence candidate produces `uncertain` if nothing else passes. Errors are explicit and never enable offline mode. The internal no-match Choice option helps ranking, but the verification stage is still executed to avoid turning first-stage rejection into a false guarantee.

## Bounds and caching

Config fields and validation live in `src/jev_skill_router/config.py`. Notable defaults: focused state <= 6,000 encoded bytes; complete Jev request <= 24,000 encoded bytes; shortlist 3 per shard; 32 actual HTTP attempts per route including retries; at most 3 concurrent requests; 4,096 indexed skills; 12,000 returned instruction characters per route; two retries for selected transient statuses; 15 seconds per complete HTTP request; 45 seconds of overall routing budget.

The code preflights a worst-case verification-call estimate before requests. Actual HTTP sends, including retries, consume a shared runtime allowance. Ranking batches run concurrently; verification starts only after ranking succeeds. Results are combined in catalog order. Asynchronous network requests and queued work are cancelled on failure or deadline, and cancellation is awaited before returning. Already accepted provider requests may still be billed; cancellation does not undo server work. Filesystem scans and local CPU work are checked at phase boundaries and cannot be preempted by the network deadline. Constructor-time initial catalog loading is outside the route timer.

Each persistent router process has an in-memory cache of at most 128 exact state/config/catalog combinations, with a default 180-second lifetime. It stores selection decisions, not a disk transcript. Content is reread when returned. CLI and hook processes are independent; no cross-process cache or full conversation tracking is claimed.

`routing_seconds` measures current selection/cache lookup time, including on cache hits. `elapsed_seconds` includes current catalog refresh and selected-file reads. A cache hit preserves its original selection time separately as `original_routing_seconds`. `http_requests` includes retries; `api_calls` retains its logical-call meaning for compatibility. Missing usage on any attempted request makes total `usage` unknown. `router.last_metrics` provides local phase timings, file-reuse counts and transport counters even when a route fails; these diagnostics are not injected into every main-model response.

## Loading versus execution

The MCP interface is one static tool with `route` and `read` actions. The full catalog is never returned by `tools/list`. A CLI-only `list` command supports local administration; do not paste its output into the main-model context when trying to save space.

A selected response includes `base_directory` and `next_offset`. Local references are read with `read`. Binary assets and cross-directory references are not exposed through this reader. The host can use its separately authorized filesystem/execution tools when appropriate. Parking a skill can break references outside its own folder or assumptions about the original install path; inspect such skills before moving them.

No shell-execution API is exposed by the router. No call uninstalls plugins or changes approval policies. Setup registers the MCP entry and, for Claude/Codex, one small bridge. The optional Claude hook receives the user prompt and injects the same selected content before the main model request; the bridge tells the model not to route twice for the same task.

## Minimal custom harness example

```python
from jev_skill_router.config import Config
from jev_skill_router.router import Router

router = Router(Config.load())
try:
    result = router.route("Profile the CSV file for duplicates")
    # Append only selected instructions to a lower-priority tool/context message.
    # Do not replace your system policy or give skill text higher instruction priority.
    selected_context = [item["content"] for item in result["selected"]]
    # Your application passes selected_context to its own model/executor.
finally:
    router.close()
```

A custom harness must keep its existing catalog out of the main prompt itself. This library does not patch an arbitrary model client or hosted service.

The synchronous router owns a persistent asynchronous HTTP pool and event loop. Use one router from one calling thread. An asynchronous host should serialize calls to a shared router and use `asyncio.to_thread`; do not nest its synchronous API inside an already running event loop or run concurrent calls against the same instance.

## Source map

| Module | Responsibility |
| --- | --- |
| `config.py` | Validated settings, atomic JSON, OS credential lookup |
| `catalog.py` | Discovery, metadata parsing, safe bounded text reads |
| `jev.py` | Actual REST shape, pooling, retries, response validation |
| `router.py` | Sharding, ranking, verification, abstention, cache |
| `evidence.py` | Bounded opening/interior/ending evidence sampling |
| `mcp.py` | Static tool, JSON-RPC stdio protocol |
| `integrations.py` | Host registration, configuration merge, optional hook |
| `migration.py` | Dry-run parking, rollback, conflict-aware restore |
| `measurement.py` | Local byte accounting without inference |
| `cli.py` | Installation-facing commands and diagnostics |
