# Contributing

Use Python 3.11+. Install `.[dev,protocol]`, run `python -m pytest -q`, and reproduce `python scripts/benchmark_context.py` before changing accounting claims. Fixtures exercise the actual HTTP schema and stdio process; they do not demonstrate model accuracy.

Keep the MCP tool surface small. Do not expose the full catalog in a tool description. Preserve explicit no-match/uncertain/error behavior, existing client configuration, and the separation between reading a skill and executing its instructions. Do not silently fall back to a different provider or offline mode.

Changing the metadata rubric, excerpt size, thresholds, sharding or model version requires a new live evaluation before making quality claims. English and Korean tasks should include ambiguous and unsupported requests. API usage must be opt-in and must never depend on committed keys.

Document test scope honestly. Host adapters should gain real isolated-profile end-to-end evidence when the relevant installed client is available. The minimal MCP implementation deliberately omits resources, prompts, sampling, HTTP transport and other unused protocol surfaces.

For media, keep measurements and captions synchronized with docs/benchmark.json. Render with Remotion before calling an artifact a Remotion render. Do not ship font binaries or unlicensed music/media.

Before a version update, align both changelogs and both versioned update notes. Run `python scripts/build_release.py check`. See [release automation](docs/RELEASING.md) and [quality gates](docs/QUALITY.md).
