# Changelog

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
