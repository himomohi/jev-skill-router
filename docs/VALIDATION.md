# Validation record — 2026-09-22

This records implementation checks, not production certification or live Jev quality. The current source is version 0.3.0. Public repository: [himomohi/jev-skill-router](https://github.com/himomohi/jev-skill-router).

## Current source checks

- **199 tests passed, 2 Windows-only tests skipped, in 4.77 seconds**, Linux / Python 3.12.14. Provider responses remain fixtures, not real Jev answers.
- Revision-bound pagination covers same-length edits, truncation, reference files, CRLF/BOM and Unicode. Public MCP/CLI continuation without a digest is rejected.
- Local request planning shares live preflight, reports conservative bounds without credentials/API calls, handles empty/offline catalogs and rejects impossible plans before key lookup.
- Catalog checks cover bridge exclusion, warm cache reuse, root alias deduplication, symlink checks before normalization, unreadable subdirectory warnings and safe metadata diagnostics.
- Actual MCP subprocess tests recover from deep JSON, invalid Unicode and nonfinite frames and successfully answer a following Unicode-ID ping. Malformed provider fields and oversized numbers produce safe errors.
- Incremental catalog reuse covers new/deleted/edited files, restored modification times, same-path replacements, symlink changes, forced rehash, and changes during reads. Windows uses NTFS/ReFS change metadata when available, with full-read fallback. Native API and junction integration require Windows CI.
- Candidate-only extraction tests cover a 200-skill catalog, UTF-8/JSON request bounds and zero-spend preflight rejection. Selected-file mutation after evaluation is rejected before returning or caching its content.
- Evaluation report schema 3 aligns cold/warm route-only timing and includes failed warm attempts; schema 2 reports cannot be compared.
- Concurrent API tests verify the configured bound, preserved result order, cancellation of active/queued work on errors and deadlines, actual HTTP limits including retries, and unknown usage after failed attempts.
- Long-body evidence tests confirm relevant late text and final constraints can be included within the existing character budget. This is coverage of the extraction algorithm, not proof of better model accuracy.
- Evaluation tests verify no credential lookup in preflight, actual HTTP/retry counters, cold and immediate-repeat timing, error/no-match denominators, interrupted cases, report privacy, strict pricing conditions and comparable-run ingestion.
- The evaluator preflight found **24 cases: 12 English, 12 Korean, six no-match**, over the six example skills, with **zero API calls and zero credential reads**.
- [Historical v0.2.1 local refresh measurement](runtime-benchmark.json): 200 synthetic files, five alternating runs per mode, Linux. Full-refresh median 147.313 ms; incremental median 21.975 ms; unchanged content reloads 200 → 0. This compares refresh modes of the current implementation, not live routing or total task speed.
- The current context-accounting artifact includes the revision-aware schema/read envelope: 200 skills, 58,088 → 4,845 bytes (91.66%). Five skills increase the modeled payload by 24.88%.

## v0.3.0 cross-platform CI

[CI run 35737405992](https://github.com/himomohi/jev-skill-router/actions/runs/35737405992) passed all four jobs for commit [`f1e0607`](https://github.com/himomohi/jev-skill-router/commit/f1e0607d98ccacf700e198ce71e75bc27c60179e). The subsequent validation-record update changes documentation only.

| Environment | Test result | Context benchmark / evaluator preflight |
| --- | --- | --- |
| Ubuntu / Python 3.11 | 199 passed, 2 Windows-only skipped | Passed |
| Ubuntu / Python 3.13 | 199 passed, 2 Windows-only skipped | Passed |
| macOS / Python 3.12 | 199 passed, 2 Windows-only skipped | Passed |
| Windows / Python 3.12 | 201 passed | Passed |

Each job also built and installed the package from source. This establishes the tested Python/OS behavior, including native Windows catalog checks; real host UI sessions, keychain use and paid Jev inference remain outside the CI scope. The older CI results below are historical.

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

The first 0.3.0 CI run exposed a Windows-specific assumption in the new symlink-normalization regression fixture: Windows and POSIX resolved its cross-directory `..` differently before the behavior under test ran. The fixture now points to a sibling directory under the same parent, so both platforms resolve to the same intended root and still verify rejection of the original symlink component. The runtime path checks were unchanged.

## Not verified

- Live Jev authentication, semantic accuracy, Korean routing quality, inference latency or actual billed cost. No live request was made during these checks.
- Real Codex, Claude Code or Cursor installation and use. Generated configuration and local subprocess tests do not establish real host compatibility. Disable or remove native skill exposure separately and start a new session.
- Real macOS Keychain, Windows Credential Manager or Linux Secret Service behavior. Code has no plaintext key fallback, but OS credential-store integration needs live platform testing.
- The current 91.66% comparison for 200 skills measures only synthetic skill-related UTF-8 payload (58,088 versus 4,845 bytes), not total context, tokens, cost or speed. The historical v0.1.0 illustration used 92.41%. Small catalogs can have greater overhead.

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

현재 소스의 로컬 테스트 199개를 통과했고 Windows 전용 테스트 2개는 로컬에서 건너뛰었습니다. 파일 버전을 확인하는 이어 읽기, 무과금 요청 사전 점검, 안내용 스킬의 자기 선택 방지, 중복 경로 통합과 MCP 입력 오류 복구를 보완했습니다. 영어·한국어 24개 사례의 사전 점검은 키 조회와 API 호출 없이 통과했습니다. 현재 0.3.0 코드의 네 CI 환경을 모두 통과했습니다. Windows에서는 201개 전부, Ubuntu 3.11/3.13과 macOS에서는 각각 199개 통과·Windows 전용 2개 제외입니다. 검증 커밋은 f1e0607이며 실제 API 호출은 포함하지 않았습니다.

실제 Jev 인증·판단 품질, 사용자 하네스 실행, 운영체제 키체인은 아직 검증하지 않았습니다. 현재 91.66%는 합성 데이터의 스킬 관련 바이트 감소이며 실제 비용·속도 개선율이 아닙니다. 로컬 파일 처리 개선과 모델·전체 작업 성능은 구분해야 합니다.
