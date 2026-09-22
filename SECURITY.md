# Security and privacy boundaries

**Register only trusted skill directories. This is a reader/router, not a sandbox for malicious skills.**

## What leaves the machine

Live routing sends the focused task, supplied recent context, skill names/descriptions, and shortlisted instruction excerpts to `https://api.typesafe.ai/v1/systemone`. The full conversation is not read automatically. API keys are sent only in the Authorization header to that fixed HTTPS endpoint; redirects are not followed. Review TypeSafe's current legal/data-processing policies before using confidential content.

Excerpts can now include interior and final portions of a long body, not only its beginning. Review the entire registered skill for sensitive content. Excerpt sampling is not redaction.

The code does not reliably detect or redact every secret in a task or skill. Do not put secrets in either. There is no telemetry uploader or persistent routing transcript. The in-memory cache contains task-derived hashes and decisions and disappears with the process. A CLI result or host conversation may still store returned skill content; host logging is outside this server's control.

## Credentials

`auth` uses an explicitly supported OS keychain backend. Unsupported backends are rejected; no plaintext fallback. Environment credentials are supported. Configuration, fixtures, examples and committed reports contain no real API keys. A key stored under an OS account is available to processes with that account's applicable keychain permissions; this tool is not a defense against a compromised account.

## File access

Reads are bounded UTF-8 text from known skill directories. Absolute paths, parent traversal, hidden paths, symlinks, unsupported extensions and some secret-like names are rejected. Parsing uses safe YAML loading. Binary assets and references outside the selected directory require the host's separately authorized tools.

This is not a hardened filesystem sandbox: a malicious local process able to change paths concurrently may race checks, hard links are not a separate isolation boundary, and allowed text files may contain sensitive content under innocuous names. Do not make untrusted shared directories available to this process. Discovery can read multiple large files, so cap root scope for large/hostile collections.

On Linux/macOS, unchanged parsed catalog entries may be reused after identity, size and timestamp checks. A filesystem that preserves/spoofs all observed metadata can defeat this optimization's change detection; use `Catalog.refresh(force=True)` where metadata is unreliable. Windows conservatively rereads files. Selected content is always read again and path-checked.

## Model decisions do not grant permission

Skill excerpts can contain prompt injection. Decision prompts tell Jev to treat them as data, but that is not a complete prompt-injection defense. Validate trust before registration. The router exposes no execute/shell tool and never automatically installs or runs a selected script. The host's higher-priority policy, sandbox and approval requirements remain in force.

## Mutations

Setup, auth and park/restore are explicit local administration commands. MCP route/read are read-only aside from memory state and outgoing inference requests. Parking needs `--apply`, records a manifest, and attempts rollback. Restoring an untrusted edited manifest is not supported as a secure workflow. Configuration/skills may be only partially changed after a crash or an external client's registration failure; read the output and use backups.

The publishing helper requires an explicit public/private choice, refuses existing remotes/repos, and scans a small set of recognizable credential formats. That scan is **not** a comprehensive secret audit. Review all files before public publication; do not publish confidential skill libraries, local config files or generated private evaluations.

## Reporting

Do not file a public issue containing credentials, private skills or a working exploit against a third-party service. Use the repository owner's private security reporting channel when configured. No private reporting address is invented in this source bundle.
