# Validation record — 2026-09-22

This records implementation checks, not production certification or live Jev quality. The current source is version 0.2.1. Public repository: [himomohi/jev-skill-router](https://github.com/himomohi/jev-skill-router).

## Current source checks

- **136 tests passed, 2 Windows-only tests skipped, in 2.96 seconds**, Linux / Python 3.12.14. Provider responses remain fixtures, not real Jev answers.
- Incremental catalog reuse covers new/deleted/edited files, restored modification times, same-path replacements, symlink changes, forced rehash, and changes during reads. Windows uses NTFS/ReFS change metadata when available, with full-read fallback. Native API and junction integration require Windows CI.
- Candidate-only extraction tests cover a 200-skill catalog, UTF-8/JSON request bounds and zero-spend preflight rejection. Selected-file mutation after evaluation is rejected before returning or caching its content.
- Evaluation report schema 3 aligns cold/warm route-only timing and includes failed warm attempts; schema 2 reports cannot be compared.
- Concurrent API tests verify the configured bound, preserved result order, cancellation of active/queued work on errors and deadlines, actual HTTP limits including retries, and unknown usage after failed attempts.
- Long-body evidence tests confirm relevant late text and final constraints can be included within the existing character budget. This is coverage of the extraction algorithm, not proof of better model accuracy.
- Evaluation tests verify no credential lookup in preflight, actual HTTP/retry counters, cold and immediate-repeat timing, error/no-match denominators, interrupted cases, report privacy, strict pricing conditions and comparable-run ingestion.
- The evaluator preflight found **24 cases: 12 English, 12 Korean, six no-match**, over the six example skills, with **zero API calls and zero credential reads**.
- [Local refresh measurement](runtime-benchmark.json): 200 synthetic files, five alternating runs per mode, Linux. Full-refresh median 147.313 ms; incremental median 21.975 ms; unchanged content reloads 200 → 0. This compares refresh modes of the current implementation, not live routing or total task speed.
- The current context-accounting artifact includes new timing/request fields: 200 skills, 58,004 → 4,463 bytes (92.31%). Five skills increase the modeled payload by 17.58%.

The historical CI below applies to its cited earlier commit. A new local pass does not establish that every platform has run the current source.

## Historical v0.2.0 CI

[CI run 35692027500](https://github.com/himomohi/jev-skill-router/actions/runs/35692027500) passed all four jobs: Ubuntu Python 3.11/3.13, Windows Python 3.12 and macOS Python 3.12. This predates the current changes. Current-commit results are available in the [test workflow](https://github.com/himomohi/jev-skill-router/actions/workflows/test.yml).

## Historical v0.1.0 checks

| Check | Observed result | Boundary |
| --- | --- | --- |
| Local Python suite | **72 passed in 2.00 seconds**, Linux / Python 3.12.14 | TypeSafe responses are HTTP fixtures, not live model answers. |
| [GitHub CI](https://github.com/himomohi/jev-skill-router/actions/runs/35685705223) | All four jobs passed: Ubuntu Python 3.11 and 3.13, macOS Python 3.12, Windows Python 3.12 | Tests and synthetic benchmark; no real desktop client or keychain session. Tested code commit `63d31214e5e827dfc0bf4e480cd85dab7ac98b6e`. |
| Clean dependency installation | Fresh virtual environment installed `.[dev,secure]` from registry dependencies | Linux installation, not a clean Windows/macOS guided-install test. |
| Guided installer | `Install.py --offline --non-interactive --client none --no-keychain` succeeded in a separate temporary application directory | Runtime, six example skills, launcher, non-live doctor and a Python-debug route checked. No user client configuration or native skills changed. |
| MCP stdio and Claude hook | Actual subprocess initialization, tool listing, routing, selected-file reading, hook input/output and error paths passed | Not an official MCP conformance suite or a real host UI test. |
| CSV example | Offline selector chose `csv-profile`; host executed the bundled read-only script and checked four rows, one duplicate, missing counts `[0, 1, 2]` | No Jev call; router does not execute scripts. [Recorded result](demo-run.json). |
| Context comparison | Committed counts and hashes reproduced for 5/50/200/500 synthetic skills | UTF-8 bytes, not model tokens, billing, latency or routing quality. [Method](BENCHMARKS.md). |
| [Remotion build and render](https://github.com/himomohi/jev-skill-router/actions/runs/35685682423) | `npm ci`, dependency-backed TypeScript check and both EN/KO renders succeeded | Rendered source commit `b4910f477e741ff6a573374c4f6b39b6d032aeef`; video code unchanged by later test/docs updates. |
| Remotion video inspection | Both outputs: 1280×720, 24 fps, 720 frames; five scenes per language visually inspected | 30 seconds of video, approximately 30.06-second container duration. Conceptual animation, not a live product recording. Release files: `overview.en.mp4`, `overview.ko.mp4`. |
| Separate previews | EN/KO Pillow + FFmpeg previews and posters inspected | Repository `preview.*.mp4` files are not Remotion outputs. |

The workflow artifact ZIP has SHA-256 `b0a61057e3821d31262d7a1fd9d8c8bcd5437aff7adf4485c58e084631e60c31`; the downloaded archive matched it.

## Test coverage and corrected issues

Catalog metadata, all six example skills, duplicates, malformed files, bounded reads, symlink/traversal rejection, exact LF/CRLF pagination, and file-hash cache invalidation are covered. Windows CI initially exposed universal-newline normalization in the pagination test's expected text. The test now writes and compares explicit LF and CRLF byte content; runtime behavior was unchanged, and all four CI jobs then passed.

Provider fixtures exercise documented request/response shapes, independent verification, malformed answers, invalid probabilities, authentication failure, retries and request budgets. Routing covers no-match, abstention, confidence/fit gates, a 270-skill sharding case, explicit offline labeling and caching. Setup/migration checks cover preserved settings, dry-run/apply/restore and collision refusal.

Earlier validation also corrected a YAML description with an unquoted colon and a missing-config hook error. Regression tests cover both.

## Not verified

- Live Jev authentication, semantic accuracy, Korean routing quality, inference latency or actual billed cost. No TypeSafe API key was available; no live request was made.
- Real Codex, Claude Code or Cursor installation and use. Generated configuration and local subprocess tests do not establish real host compatibility. Disable or remove native skill exposure separately and start a new session.
- Real macOS Keychain, Windows Credential Manager or Linux Secret Service behavior. Code has no plaintext key fallback, but OS credential-store integration needs live platform testing.
- The current 92.31% comparison for 200 skills measures only synthetic skill-related UTF-8 payload (58,004 versus 4,463 bytes), not total context, tokens, cost or speed. The historical v0.1.0 illustration used 92.41%. Small catalogs can have greater overhead.

## Reproduce

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/benchmark_context.py
python scripts/benchmark_runtime.py --synthetic-skills 200
python scripts/evaluate_live.py --preflight
python Install.py --offline
```

See [video instructions](../video/README.md) for rendering and [publishing](PUBLISHING.md) for release details. For live provider verification, configure a local key with `jev-skills auth` or server-side `TYPESAFE_API_KEY`, select live mode, then run `jev-skills doctor --live`. The optional evaluator requires `--allow-live` and incurs API usage. Never commit an API key.

## 한국어 요약

현재 소스의 로컬 테스트 136개를 통과했고 Windows 전용 테스트 2개는 로컬에서 건너뛰었습니다. 변경 없는 파일 재사용, 본문 여러 구간의 검증 근거, 동시 API 요청·시간 및 요청 한도, 실측 도구를 보완했습니다. 영어·한국어 24개 사례의 사전 점검은 키 조회와 API 호출 없이 통과했습니다. 위 Linux·macOS·Windows CI 기록은 명시된 이전 커밋의 결과입니다.

실제 Jev 인증·판단 품질, 사용자 하네스 실행, 운영체제 키체인은 아직 검증하지 않았습니다. 현재 92.31%는 합성 데이터의 스킬 관련 바이트 감소이며 실제 비용·속도 개선율이 아닙니다. 로컬 파일 처리 개선과 모델·전체 작업 성능은 구분해야 합니다.
