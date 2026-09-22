[**English**](README.md) | [한국어](README.ko.md)

# Jev Skill Router

### Your skills belong in a library. Not in every prompt.

**Keep the skill catalog outside your main LLM's context. Let Jev select what to load.**

A small, local Python service reads your trusted `SKILL.md` library, asks [TypeSafe Jev](https://docs.typesafe.ai/introduction) which skills actually fit, and returns only selected instructions through **one MCP tool**. Your existing agent still does the work, using its normal tools and approval rules.

**Python 3.11+ · Claude Code / Codex / Cursor adapters · English + Korean docs · MIT**

**0.3.0 update:** [What's changed and how to upgrade](docs/updates/v0.3.0.md) · [Changelog](CHANGELOG.md)

[![Context comparison: synthetic skill-related UTF-8 payload, not model tokens](docs/media/poster.en.png)](https://github.com/himomohi/jev-skill-router/releases/download/v0.1.0/overview.en.mp4)

[English overview](https://github.com/himomohi/jev-skill-router/releases/download/v0.1.0/overview.en.mp4) · [한국어 영상](https://github.com/himomohi/jev-skill-router/releases/download/v0.1.0/overview.ko.mp4)

> **Early release:** live Jev routing quality and end-to-end use in supported clients are still being validated.

## Why another layer?

Progressive-disclosure harnesses usually load skill **names and descriptions**, not every full skill body, at startup. That is already better than loading everything, but an index containing hundreds of descriptions still consumes context. [Agent Skills specification](https://agentskills.io/specification).

This project moves the **selection inventory**, not merely the bodies, outside the main model. Its main-model footprint is approximately a fixed router interface plus the selected content: **O(1) + O(k loaded content)** rather than **O(N catalog metadata) + O(k loaded content)**. Jev still reads the metadata; the work moves to a separate decision service, not into thin air.

**Important: adding an MCP server alone does not hide native skills.** Disable their native exposure or explicitly move user-managed skill folders out of the harness's discovery paths. Start a **new session** to avoid carrying the old inventory in conversation history. Hosted ChatGPT's built-in/plugin inventory is not something this local server can remove.

## Start with the bundled examples

Download and extract the [latest source ZIP](https://github.com/himomohi/jev-skill-router/archive/refs/heads/main.zip), install **Python 3.11+**, then run:

```bash
python Install.py --offline
```

On Windows, open `Install.cmd`; on macOS, run `bash Install.command`. The guided installer asks for a skill root and client, creates a private environment in `~/.jev-skill-router/runtime`, and prints a stable CLI launcher. With no root, it copies six bundled example skills into the app's data directory. Network access is needed to install Python dependencies, even for the offline demo.

**Offline is an explicitly labeled keyword demonstration, not Jev.** It validates the installation and loading path without pretending to reproduce model behavior.

Already using uv? From the extracted repository:

```bash
uv tool install '.[secure]'
jev-skills setup --root ./examples/skills --offline
jev-skills route "Debug a Python traceback and failing tests"
```

No published PyPI package is assumed. `pip install jev-skill-router` is **not** the installation instruction for this source release.

## Connect your real library

A practical Codex setup, after installing the CLI:

```bash
jev-skills setup --root ~/.agents/skills --client codex
jev-skills auth
jev-skills doctor --live

# Inspect first. Nothing moves without --apply.
jev-skills park ~/.agents/skills
jev-skills park ~/.agents/skills --apply
```

`auth` stores the key only in a supported OS keychain: macOS Keychain, Windows Credential Manager, or a supported Linux Secret Service backend. It never falls back to a plaintext key file. Alternatively provide `TYPESAFE_API_KEY` in the **server's** environment. `doctor --live` makes a real API request; key presence by itself is not proof of authentication.

`park` preserves the router bridge and `.system` directory, moves direct user-managed skill folders to an external vault, updates router roots, and writes a restoration manifest. It does **not** manage plugin registries, nested collections, system packages, or cross-skill dependencies. Review the dry run and make a backup first. [Exposure and recovery](docs/INSTALLATION.md).

Prefer not to move files? Codex supports disabling local skills using `[[skills.config]]` entries; keep the original paths registered with this router. [Official local-skill configuration](https://developers.openai.com/codex/skills).

| Integration | Setup | Behavior |
| --- | --- | --- |
| Codex | `setup --root PATH --client codex` | MCP registration plus one bridge skill; the model chooses to call the router |
| Cursor | `setup --root PATH --client cursor` | Preserving merge into `~/.cursor/mcp.json`; on-demand MCP use |
| Claude Code | `setup --root PATH --client claude` | MCP registration plus a bridge skill |
| Claude pre-turn hook | Add `--hook` to Claude setup | Runs routing before each submitted user prompt; injects selected instructions |
| Your own harness | Import `Router`, call `.route(task)` | You control exactly when selected content enters the next model request |

Codex/Cursor MCP integration is **not** universal prompt interception. Claude's optional hook gives a concrete pre-turn path, but makes additional Jev calls even for prompts where nothing matches. It does not alter the host's permissions.

## What happens on a request?

```mermaid
flowchart TD
    A[Focused task] --> B[Jev: rank external metadata]
    C[(Trusted local skills)] --> B
    B --> D[Jev: verify shortlisted evidence]
    D --> E{Fit + confidence gates}
    E -->|Pass| F[Load selected SKILL.md only]
    E -->|Uncertain / no match| G[Load nothing]
    F --> H[Your agent executes with its own tools]
```

Jev first selects candidates from skill metadata, then checks their relevance against instruction excerpts. If no candidate meets the fit and confidence thresholds, no skill is loaded. Small catalogs normally need two logical API requests; larger catalogs require more. Independent batches run up to three at a time. A 45-second routing deadline and a 32-request cap, including retries, bound the default live route. [Settings](docs/INSTALLATION.md#routing-limits).

The default returns at most **one** skill; set `max_skills` to 2 or 3 for broader tasks. Low fit, low confidence, malformed API responses, missing keys, and API failures do not silently substitute another model or keyword routing.

## How much context can this save?

**Locally reproduced synthetic accounting. UTF-8 bytes, not model tokens.** These numbers measure only the skill-related serialized content in **one main-model context after loading the same selected skill**. They are not a whole-conversation or billing benchmark.

| Skills | Progressive baseline: metadata + selected body | Router: interface + call + bookkeeping + same body | Reduction |
| ---: | ---: | ---: | ---: |
| 5 | 3,878 | 4,843 | -24.88% |
| 50 | 16,388 | 4,844 | 70.44% |
| 200 | 58,088 | 4,845 | 91.66% |
| 500 | 141,488 | 4,845 | 96.58% |

**Five skills are worse, not better:** the extra interface outweighs a tiny inventory. The benefit grows with catalog size and description length. Large conversation histories, large selected bodies, already-deferred discovery, and repeated MCP calls change the overall result. Cached metadata can also be cheap; less context does not guarantee a smaller bill or faster task completion.

Measure your own library without making an API call:

```bash
jev-skills benchmark
jev-skills benchmark --skill python-debug
```

[Comparison method and limitations](docs/BENCHMARKS.md)

## Check readiness before an API call

```bash
jev-skills plan "Debug a Python traceback and failing tests"
```

This local preflight reports ranking/verification request bounds, retry headroom and blocking limits without reading your key or contacting Jev. It shares the live router's planning code. A ready plan means the local limits fit; authentication and decision quality still need live evaluation. [Plan output and exit codes](docs/INSTALLATION.md#check-a-route-before-spending).

Long-file reads return a `content_digest`. Continue with the returned `next_offset` and `expected_digest=content_digest`; version 0.3.0 requires the digest for continuation so file edits cannot silently mix pages. The router's own bridge is excluded from candidates, and equivalent root paths are deduplicated.

## Test your own workload

```bash
# Validate the 24 English/Korean example cases without an API call
python scripts/evaluate_live.py --preflight
# After configuring your key: real requests, capped including retries
python scripts/evaluate_live.py --allow-live --max-requests 64
```

The report separates selection quality, fresh/cache-hit latency, HTTP requests and reported usage. It does not claim to measure final task success or the main model’s total bill. [Evaluation and comparisons](docs/EVALUATION.md).

## Use it

After connecting your client, start a new session and ask it to use the skill router for your task, for example:

> Use the skill router to find guidance for debugging this Python traceback.

You can also check skill selection from your terminal:

```bash
jev-skills route "Debug a Python traceback and failing tests"
```

The router returns selected instructions and relevant local references for your agent to use. [Tool interface](docs/ARCHITECTURE.md).

The router does **not** execute scripts, install arbitrary packages, modify application data, or grant permissions. Skills are read-only guidance; the agent's existing executor performs authorized actions. Reads are confined to trusted skill directories, block traversal and symlinks, and accept bounded UTF-8 text. This is not a sandbox for hostile local files or untrusted skill authors.

## Convenience without hidden behavior

One external library can serve several local harnesses. Catalog files are parsed locally; only selected instructions are returned to the main model. Linux/macOS reuse unchanged parsed files; Windows uses native NTFS/ReFS change timestamps and falls back to full reads when unavailable. A persistent MCP process reuses its HTTP pool and exact-request cache. Separate CLI invocations and Claude hook processes do **not** share that cache.

Configuration is local JSON, keys stay out of that JSON, and the provider endpoint is fixed to TypeSafe HTTPS. Live requests disclose focused task text, skill descriptions, and shortlisted excerpts to TypeSafe. Do not register confidential material without permission. [Security](SECURITY.md).

[Installation and recovery](docs/INSTALLATION.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
