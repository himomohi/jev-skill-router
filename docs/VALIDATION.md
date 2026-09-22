# Validation record — 2026-09-22

Version 0.1.0. This records implementation and artifact checks, not production certification or live Jev quality. Public repository: [himomohi/jev-skill-router](https://github.com/himomohi/jev-skill-router).

## Executed checks

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
- The 92.41% comparison for 200 skills measures only synthetic skill-related UTF-8 payload (58,004 versus 4,403 bytes), not total context, tokens, cost or speed. Small catalogs can have greater overhead.

## Reproduce

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/benchmark_context.py
python Install.py --offline
```

See [video instructions](../video/README.md) for rendering and [publishing](PUBLISHING.md) for release details. For live provider verification, configure a local key with `jev-skills auth` or server-side `TYPESAFE_API_KEY`, select live mode, then run `jev-skills doctor --live`. The optional evaluator requires `--allow-live` and incurs API usage. Never commit an API key.

## 한국어 요약

로컬 테스트 72개와 Linux·macOS·Windows CI를 통과했습니다. 전용 설치 프로그램, MCP·훅 프로세스, 예제 실행을 확인했고 영어·한국어 Remotion 영상을 실제 렌더링해 각 5개 장면을 검토했습니다. 공개 저장소와 v0.1.0 릴리스에서 소스와 영상을 제공합니다.

실제 Jev 인증·판단 품질, 사용자 하네스 실행, 운영체제 키체인은 아직 검증하지 않았습니다. 92.41%는 합성 데이터의 스킬 관련 바이트 감소이며 실제 비용·속도 개선율이 아닙니다.
