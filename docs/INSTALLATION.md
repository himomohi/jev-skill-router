# Installation, native exposure, and recovery

## Prerequisites

Python 3.11 or later and internet access for dependency installation. For live routing, a TypeSafe account/API key with access to the selected model. For host integration, an installed Claude Code/Codex CLI or Cursor. Remotion rendering is separate and needs Node.js 20+ plus npm dependencies and a supported Chrome/Chromium renderer.

The guided installer creates a user-local virtual environment; it does not modify the system Python, install Node, remove native skills, or disable OS security controls. Local build tests reused preinstalled Python dependencies because external package downloads were unavailable. Fresh network-based installs and Windows/macOS host installations have not been tested here.

## Guided installation

From the extracted source directory:

```bash
python Install.py
```

Use `python3` on systems where that is the Python 3 command. Windows wrapper: `Install.cmd`. macOS wrapper: `bash Install.command`. An unavailable Python executable must be installed first; do not disable Gatekeeper or execution protections merely to run the wrapper.

Useful explicit modes:

```bash
python Install.py --root ./examples/skills --offline --client none
python Install.py --root ~/.agents/skills --client codex --auth --verify
python Install.py --root ~/.claude/skills --client claude --hook --auth
```

`--auth` prompts for a key in the local terminal and saves it only in the OS keychain. `--verify` makes a real API diagnostic call. `--no-keychain` installs only core dependencies for environment-based credentials. `--non-interactive` suppresses installer questions. Installing from source still needs Python packaging dependencies; offline demo means no inference, not zero network during first install.

A generated launcher is printed at the end, usually `~/.jev-skill-router/bin/jev-skills` or its Windows `.cmd` equivalent. Add the containing directory to PATH, or use the absolute launcher path. The installer does not silently rewrite shell startup files. The registered MCP process uses an absolute Python path, so it does not require shell activation.

## Existing Python / uv environment

```bash
uv tool install '.[secure]'
# or, in a virtual environment:
python -m pip install '.[secure]'

jev-skills setup --root /absolute/path/to/external-skills
jev-skills auth
jev-skills doctor --live
```

Configuration defaults to `~/.jev-skill-router/config.json`. Set `JEV_SKILLS_HOME` or use `jev-skills --config /path/config.json COMMAND` to isolate profiles. The global `--config` flag goes **before** the subcommand. Fresh setup defaults to live mode. Repeating setup preserves the existing mode; use `--live` or `--offline` to switch explicitly. No key is written into config JSON.

## Routing limits

Existing configuration files use the defaults for new fields. Adjust these fields in your local config JSON:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `max_concurrency` | 3 | Independent requests at once; use 1 for serial operation |
| `route_timeout_seconds` | 45 | Shared routing time budget; asynchronous network work is cancelled on expiry |
| `timeout_seconds` | 15 | Maximum time for one HTTP request |
| `max_api_calls` | 32 | Actual HTTP attempts per route, **including retries** |
| `excerpt_chars` | 900 | Total evidence characters per skill, sampled across long bodies |
| `cache_seconds` | 180 | Exact repeated-decision lifetime in one process |
| `candidate_strategy` | `all` | Complete catalog or explicit `indexed` lexical narrowing |
| `candidate_limit` | 64 | Maximum retained metadata candidates when indexing applies (8–512) |

Retrying consumes the same request allowance; missing usage remains unknown. Local filesystem work is checked between phases, so a blocked filesystem can exceed the time budget. Lower concurrency if the provider returns rate limits. [Real workload evaluation](EVALUATION.md) records accuracy, delays and every attempted request before you decide whether routing helps.

### Check a route before spending

```bash
jev-skills plan "Debug Python tracebacks" --context "Only the failing unit test"
```

`plan` reads the local catalog, uses the same packing and verification bounds as live routing, and returns `ready`, `rank_requests`, `verification_requests_upper_bound`, `base_requests_upper_bound` and `http_requests_upper_bound`. It never looks up credentials or calls the provider. Exit code 0 means the local plan fits; 1 means an empty catalog or a blocking budget; 2 means invalid input/configuration. Review `warnings` even when `ready` is true: unreadable or malformed skills cannot participate.

The plan assumes a fresh decision, even when the process already has a cached selection. Retry headroom is the HTTP cap minus the conservative base-call bound. It does not promise that every retry can complete, validate authentication, predict which skill will win, or estimate money/latency. Offline plans report zero provider requests. No catalog is exposed through the MCP tool listing.

### Continue a long file without mixing revisions

Each selected skill or file read includes `content_digest`, `next_offset` and `path`. Keep the digest for **that file** when requesting its next page:

```json
{"action":"read","skill_id":"s_ID_FROM_ROUTE","path":"SKILL.md","offset":12000,"expected_digest":"COPY_THE_64_CHARACTER_CONTENT_DIGEST"}
```

Use the actual `next_offset` and digest from the preceding result. From the CLI, pass `--offset OFFSET --expected-digest DIGEST`. Starting with version 0.3.0, an offset greater than zero without the digest is rejected. If the file changes, discard the partial content and restart at offset zero, or reroute a changed `SKILL.md`. A reference file has its own digest; do not reuse the parent skill's digest for it. Existing first-page reads remain supported.

## Credentials for GUI-launched hosts

GUI apps often do not inherit variables exported in a terminal. Prefer `auth` with the supported OS keychain and the same OS user as the MCP server. If a keychain is locked/unavailable, the command reports failure rather than saving a plaintext fallback.

For environment credentials, ensure `TYPESAFE_API_KEY` reaches the server. For Codex, the generated `config-snippet` includes `env_vars = ["TYPESAFE_API_KEY"]`. Registration through `codex mcp add` does not automatically append that field, so users choosing environment credentials must review their entry. It is unnecessary when the keychain works. Never copy a real key into a public config or command argument.

Changing a key during a persistent server process requires restarting that MCP process, because it may retain its existing HTTP client's authorization header.

## Remove duplicate native exposure

### Option A: explicit parking, with preview

```bash
jev-skills park ~/.agents/skills
jev-skills park ~/.agents/skills --apply
```

Only immediate nonhidden child directories containing `SKILL.md` move. `.system`, the `jev-skill-router` bridge, nested collections without a direct `SKILL.md`, and symlinked directories are not moved. Do not use this on package-manager-owned or plugin-managed folders. Whole skills and internal references move together, but paths outside each skill may need attention.

The external destination is `~/.jev-skill-router/vault/<migration-id>/`. A manifest records moves and the config path. Successful parking adds the vault root. Other harness installations sharing the original path may lose native discovery too; that is the purpose of moving files, so review the impact first.

The metadata name `jev-skill-router` is reserved for the native bridge and excluded from routing candidates. Its file stays available to the host; it cannot consume a selection slot after parking. Use a different name for an ordinary skill. Equivalent root paths are deduplicated; refresh/reroute to obtain current IDs if older configuration used paths containing `..`.

Close/restart or begin a fresh host session. Inspect its skill listing: the original catalog should no longer appear from that root. `doctor` cannot prove absence of every plugin/system/project-level source; do not claim savings merely because setup succeeded.

### Option B: keep original files, disable native discovery

Codex supports local per-skill disabling in `~/.codex/config.toml`:

```toml
[[skills.config]]
path = "/absolute/path/to/my-skill/SKILL.md"
enabled = false
```

Keep that folder in the router's roots. Do not disable the router bridge. Other harnesses/plugins may have different controls; use their documented settings. Disabling a plugin may also remove the tools its skills need. Preserve required executors and permissions; instruction routing does not recreate an unavailable connector.

## Restore after parking

Use the exact manifest path printed by `park`:

```bash
jev-skills restore /absolute/path/to/vault/MIGRATION_ID/migration.json
jev-skills restore /absolute/path/to/vault/MIGRATION_ID/migration.json --apply
```

The first command is a preview. Restore refuses to overwrite files already recreated at the original location. It preserves roots added since migration, removes the old vault root, and registers the restored source root. Treat manifests as trusted local administrative files; do not apply a manifest supplied by an untrusted party.

The process attempts rollback on handled failures. It cannot make multi-file filesystem operations transactionally atomic across power loss/process termination. Keep your own backup and inspect both directories after a crash.

## Hook behavior

`setup --client claude --root PATH --hook` preserves other hooks and backs up settings before adding a `UserPromptSubmit` command. It uses the incoming `prompt`, not the whole transcript. Focused routing input above 6,000 encoded bytes is rejected rather than silently truncated. Routing failure injects an unavailable notice, not a skill or a blocking decision.

Claude's current documentation states very large `additionalContext` can be moved to a file by the host. Our route result can exceed its inline limit when bodies are long; the host must read the resulting file or use paginated MCP reads. Tune `max_output_chars` downward for a compact inline hook payload.

The hook starts a separate process on each prompt. Its cache and HTTP pool do not persist across prompts. It does not intercept all subagent turns or direct slash-command expansion events. Its input/output format was tested with subprocess fixtures; actual Claude invocation was not available in the build environment.

## Updating and removal

Rerun installation to update the private environment. The example library is copied only when absent, so rerunning does not overwrite edited examples. A client may reject duplicate registration; inspect `claude mcp list`, `codex mcp list`, or Cursor's MCP settings. Remove only the `jev-skills` entry before rerunning registration, or use `config-snippet` to inspect the intended command. Existing customized bridge files are not overwritten.

For removal, restore parked skills **first**, remove the `jev-skills` MCP entry through the host's normal interface, remove only the managed hook command and unchanged bridge, then remove the app runtime directory when it no longer contains needed vaults/manifests. Do not delete the whole data directory while skills are still parked there. Remove the stored `jev-skill-router` key from the operating system's credential manager when no longer needed.

## Upgrade an existing guided installation

Download the new source archive or update this checkout, then run:

```bash
python Install.py --upgrade --non-interactive
# For core-only installations using environment credentials:
python Install.py --upgrade --non-interactive --no-keychain
jev-skills --version
```

Use the same `JEV_SKILLS_HOME` as the original installation. The upgrade verifies the installed package version and runs local diagnostics. It preserves config bytes, roots, routing mode, credentials, client registration and custom launchers; it does not rerun setup/authentication. Restart the host session. An existing configuration makes a fresh installation stop with an upgrade instruction. `--verify` explicitly adds one live diagnostic request.

For a pip-managed environment, run `python -m pip install --upgrade '.[secure]'` from the new checkout. Use the same interpreter/environment as before. Repeated host registration with the same command is idempotent; a conflicting entry is preserved and reported.

## Large catalogs

```bash
jev-skills plan "Inspect specialist operation" --candidate-strategy indexed --candidate-limit 64
jev-skills route "Inspect specialist operation" --candidate-strategy indexed --candidate-limit 64
```

These flags apply only to this invocation. Persist them with `setup --root PATH --candidate-strategy indexed --candidate-limit 64`, or edit your config. The default `all` considers the complete catalog. Indexed mode can miss useful skills, particularly when the task and descriptions use different languages; an empty retrieval stops before any Jev request. Read `retrieval` in the plan/result, including cutoff ties. It is not a model confidence score. [Request-scaling evidence](SCALING.md).

## Check installed host CLIs

From the same Python environment as the installed router:

```bash
python scripts/check_host.py --client codex
python scripts/check_host.py --client claude
```

The checks use disposable host profiles, confirm idempotent registration and real MCP discovery/connection, and make no model/API calls. The direct router roundtrip is separate from host model-driven tool use. [Recorded connection evidence](host-connection-report.json).
