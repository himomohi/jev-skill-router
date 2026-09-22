# Changelog

[English](CHANGELOG.md) | [한국어](CHANGELOG.ko.md)

## 0.3.0 — 2026-09-22

[Update notes and upgrade instructions](docs/updates/v0.3.0.md) · [한국어 업데이트 안내](docs/updates/v0.3.0.ko.md)

- Add `jev-skills plan TASK [--context TEXT]`: inspect fresh-route request bounds, retry headroom and blocking limits without reading credentials or calling Jev. Live routing uses the same preflight before credential lookup.
- Return `content_digest` on every file read. **Pagination change:** MCP/CLI continuation with an offset greater than zero now requires that digest as `expected_digest` / `--expected-digest`; changed files fail before returning mixed pages. Start at offset zero or reroute to obtain a new revision.
- Exclude the reserved `jev-skill-router` bridge name from selection, including after parking. Preserve the bridge on disk and in the parser cache. Normalize/deduplicate root aliases only after checking their original paths for symlinks.
- Report unreadable discovery directories and actionable metadata errors without quoting invalid YAML contents. Setup now respects the configured catalog size limit.
- Keep MCP sessions alive after deeply nested JSON, invalid Unicode or nonfinite input. Convert malformed provider choice values, excessive numeric values and invalid model IDs into safe errors.
- Refresh synthetic context accounting to include the larger tool schema and file revision digest. These checks do not establish live Jev accuracy, speed or cost improvements.
- Verify the update on Ubuntu Python 3.11/3.13, macOS Python 3.12 and Windows Python 3.12. Windows passes all 201 tests; the other environments pass 199 with 2 Windows-only skips. [CI evidence](https://github.com/himomohi/jev-skill-router/actions/runs/35737405992).

## 0.2.1 — 2026-09-22

- Generate task-specific excerpts only for shortlisted skills. Cached character-width bounds reserve safe verification request sizes before API spending.
- Reuse unchanged Windows NTFS/ReFS files using native change time; fall back to full reads when unavailable and reject reparse-point paths.
- Reject selected files changed during model evaluation before returning content or caching the decision.
- Align cold/warm evaluation timers and report failed warm attempts. Report schema 3 intentionally rejects comparisons with schema 2.
- Pin CI actions to verified releases and run credential-free evaluator preflight on every platform.

## 0.2.0 — 2026-09-22

- Reuse unchanged catalog files on Linux/macOS; re-read changed files and invalidate routing decisions. Windows retains full reads, and `refresh(force=True)` forces a complete refresh.
- Sample candidate evidence from the beginning, end and relevant interior passages within the existing character budget.
- Process independent Jev batches concurrently (default: 3), with a shared 45-second routing budget, cancellation on failure and HTTP-attempt limits that include retries.
- Measure cold and cached latency, actual HTTP attempts, usage completeness and selection accuracy with 24 English/Korean evaluation cases. Compare compatible runs without recording task text, skill content or API keys in reports.
- Clarify context accounting and live-evaluation instructions. Synthetic context reduction is not a cost or speed improvement claim; live Jev quality and end-to-end efficiency remain unverified.

## 0.1.0 — 2026-09-22

Initial source release: external SKILL.md indexing, documented TypeSafe REST integration, sharded Choice ranking and independent Noul/Score verification, one read-only MCP tool, exact-request in-memory caching, bounded reference reads, explicit offline installation demo, OS-keychain support, host registration helpers and optional Claude pre-turn hook.

Includes dry-run parking/restore, local byte-accounting tools, opt-in EN/KO live evaluation, English/Korean documentation, guided installers, tests, Remotion source, locally rendered storyboard preview videos, and a create-only GitHub publishing helper.

Published to [GitHub](https://github.com/himomohi/jev-skill-router) with 72 passing local tests, a successful Linux/macOS/Windows CI matrix, and actual English/Korean Remotion renders. Added LF/CRLF pagination coverage after the initial Windows CI exposed newline normalization in the test. Release assets contain Remotion `overview.*.mp4`; repository `preview.*.mp4` files remain separate storyboard previews. Live Jev quality and actual host integrations remain unverified. See [validation](docs/VALIDATION.md).
