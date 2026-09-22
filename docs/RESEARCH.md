# Research and implementation decisions

Documentation checked for this build: **2026-09-22**. These are source references, not a claim that provider behavior was tested live.

## TypeSafe's actual API

[Introduction](https://docs.typesafe.ai/introduction) describes Jev as a structured decision model, not a text-completion agent. [HTTP API](https://docs.typesafe.ai/api) specifies `POST https://api.typesafe.ai/v1/systemone`, bearer authentication, and `state`, `model`, `questions`. The code uses that endpoint directly through a persistent `httpx.Client`; it does not invent an OpenAI-compatible chat endpoint or require a private SDK package index.

The typed primitives used here are Choice (a bounded option set), Noul (yes probability), and Score (ordered levels with a probability-weighted score). Choice supports at most 255 options. Our ranking uses at most 128 real candidates plus a no-match option. Score verification uses three levels.

[Models](https://docs.typesafe.ai/models) identifies `jev-latest` as the stable alias in the checked documentation, resolving to `jev-1.13.0` then. Aliases can move; route results report the response model version. The documentation distinguishes a 64k aggregate request budget from a 32k state-plus-longest-question budget. The implementation uses a much smaller **24,000 UTF-8-byte** payload cap plus a 6,000-byte focused-state limit; this is a conservative engineering budget, not an exact TypeSafe token counter. Over-budget requests fail before HTTP rather than silently truncating task intent.

[Confidence](https://docs.typesafe.ai/confidence) explains that confidence is derived from a distribution and is not an independent guarantee of correctness. Noul has no separate confidence field. This router gates on the candidate's Noul fit and **Score confidence**, not a fabricated Noul confidence.

## Relevant cookbook, different objective

The official [Skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion) experiment ranks 182 Hermes skills, verifies three candidates, and may abstain. Its published run, rendered 2026-07-31, used Jev 1.12 and Claude Haiku 4.5 on 488 requests. It reports wrong-load rates of 16.8% versus 7.3% and needless-load rates of 9.8% versus 4.0%.

Those are **the provider's experiment**, not this project's results. Crucially, the cookbook retains the main agent's original roster for prefix caching and adds a suggestion. Our design removes native exposure where the user controls it, uses explicit per-candidate verification gates, supports multiple selected skills, and shards larger catalogs. Its quality can differ in either direction. The official results cannot establish our accuracy or byte savings.

## Host interfaces

- [Agent Skills specification](https://agentskills.io/specification): YAML metadata and progressive loading. We support common `SKILL.md` layouts with a bounded parser; not every optional metadata field has execution semantics here.
- [Codex MCP](https://developers.openai.com/codex/mcp): stdio registration and server instructions. The generated CLI command follows the documented `codex mcp add NAME -- COMMAND` shape. Environment-based keys may need `env_vars = ["TYPESAFE_API_KEY"]`.
- [Codex skills](https://developers.openai.com/codex/skills): user discovery in `~/.agents/skills`, plus local skill disabling through `[[skills.config]]`.
- [Claude Code MCP](https://code.claude.com/docs/en/mcp): documented stdio/user-scope registration.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): `UserPromptSubmit` and `hookSpecificOutput.additionalContext`. The optional hook returns nonblocking diagnostics on errors; it does not return a blocking decision.
- [Cursor MCP](https://cursor.com/docs/mcp): user configuration at `~/.cursor/mcp.json`.
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): newline-delimited JSON-RPC, UTF-8, clean stdout. The small implementation covers initialization, ping and tools, not every MCP feature.

Host versions evolve. Documentation-conformant configuration and local protocol tests do not substitute for an installation test in an actual user profile.

## Media and publishing

[Remotion rendering CLI](https://www.remotion.dev/docs/cli/render) is the source for the included React/Remotion project's render commands. Direct and transitive dependencies are pinned. Both languages rendered successfully in [GitHub Actions](https://github.com/himomohi/jev-skill-router/actions/runs/35685682423); release assets named `overview.*.mp4` are the Remotion output. The separately identified `preview.*.mp4` files use Pillow/FFmpeg.

[GitHub repo creation](https://cli.github.com/manual/gh_repo_create) and [release creation](https://cli.github.com/manual/gh_release_create) define the publishing script's commands. The script requires the user's local authorized GitHub CLI and refuses an existing target. The public project is [himomohi/jev-skill-router](https://github.com/himomohi/jev-skill-router); the helper remains available for creating a separate new repository.
