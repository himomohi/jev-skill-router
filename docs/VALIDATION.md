# Validation record — 2026-09-22

This is a local implementation and artifact-validation record, **not a production certification or a live Jev benchmark**. The source is version 0.1.0. The build host ran Linux, Python 3.13.5, and Node.js 22.16.0.

## Executed checks

| Check | Observed result | Boundary |
| --- | --- | --- |
| `python -m pytest -q` | **71 passed in 3.72 seconds** | Deterministic local tests. TypeSafe responses are HTTP fixtures, not live model answers. |
| Package build and install | Wheel built, installed into a separate virtual environment, and imported from `site-packages` outside the source directory | HTTPX/PyYAML came from the build host's preinstalled packages through an explicit dependency path. This was not a clean online dependency installation. |
| MCP stdio | Actual subprocess initialization, static tool listing, routing, and selected-file reading | Minimal tools-only protocol implementation, not an official MCP conformance-suite result or a real client UI test. |
| Claude hook | Actual JSON input/output path, additional-context response, error handling and missing-config behavior | Claude Code itself was not launched. Registration and settings changes were tested using temporary paths/stubs. |
| CSV end-to-end example | Offline selector chose `csv-profile`; the local test host ran its bundled read-only script and checked four rows, one duplicate, and missing counts `[0, 1, 2]` | No Jev call. The router did not execute the script. [Recorded result](demo-run.json). |
| Context comparison | Reproducible, serialized UTF-8 byte counts for 5/50/200/500 synthetic skills | Not model-token, billing, latency or semantic-quality measurements. [Method](BENCHMARKS.md), [data](benchmark.json). |
| Python compilation | `python -m compileall -q src scripts Install.py` passed | Syntax compilation is supplementary to tests. |
| Video TypeScript | All three TSX source files passed syntax transpilation with TypeScript 5.8.3 | No dependency-backed typecheck or Remotion render was possible. |
| Supplied preview videos | English and Korean MP4s rendered with Pillow + FFmpeg: 1280×720, 24 fps, 720 frames, 30 seconds, H.264, silent | Separate preview renderer, **not Remotion output**. Both languages' five-scene storyboards and metric posters were visually inspected. |

## What the tests cover

Catalog parsing, all six bundled examples, duplicate names, malformed metadata, bounded reads, symlink and path-traversal rejection, file pagination, and changed-file cache invalidation are exercised.

The Jev adapter is tested against the documented HTTP request/response shapes, including string-valued Choice criteria, independent verification questions, unexpected answers, invalid probabilities, authentication failure, retry behavior, and bounded requests. Larger-catalog routing includes a 270-skill sharding case and request-budget preflight. These tests verify program behavior **given fixture decisions**, not whether Jev will make the right decisions.

Routing tests cover no-match, abstention, confidence/fit gates, explicit offline-mode labeling, and repeat-call caching. Setup and migration tests cover preserved settings, dry-run versus apply, restore behavior, and refusing collisions rather than overwriting another skill.

Validation found and fixed two concrete integration issues before packaging: a YAML description containing an unquoted colon, and a missing-config hook error that would otherwise have blocked the host turn. Regression tests cover both.

## Not executed / not claimed

- **Live Jev authentication, model accuracy, Korean routing quality, inference latency, and actual billed token/cost savings.** No TypeSafe API key was available, and no live request was made.
- **Real Codex, Claude Code, or Cursor installation/operation.** The integrations use their documented stdio/configuration formats, but local protocol fixtures do not replace checking a real host. Existing native skill exposure must be removed or disabled separately, then checked in a new session.
- **Real macOS Keychain, Windows Credential Manager, Linux Secret Service, or a clean Windows/macOS installation.** Key handling is guarded in code and has no plaintext fallback; platform behavior remains to be verified.
- **Remotion dependency installation, dependency-backed typecheck, and rendering.** The attempted npm installation failed with `EAI_AGAIN` resolving `registry.npmjs.org`. The editable source and a manual GitHub Actions rendering workflow are supplied. See [video/README.md](../video/README.md).
- **New GitHub repository creation, remote push, release-asset upload, or GitHub Actions execution.** The connected GitHub actions did not expose new-repository creation. The local publishing helper was attempted but stopped because GitHub CLI was absent. No remote repository URL is presented as an existing deliverable. See [publishing instructions](PUBLISHING.md).

## Reproduce locally

From the source root with Python 3.11+ and dependency-download access:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/benchmark_context.py
```

For a local, keyless integration example, use `python Install.py --offline` and the executable path printed by installation. Offline mode is intentionally labeled lexical demonstration mode; it is not a substitute for validating Jev.

For a real provider check, store your API key locally with `jev-skills auth` or provide `TYPESAFE_API_KEY` to the server process, switch the setup to live mode, then run `jev-skills doctor --live`. Optional labeled-case evaluation is provided by `scripts/evaluate_live.py`; it requires explicit `--allow-live` and can incur API charges. Never paste an API key into a public issue or commit.

## 한국어 요약

로컬 테스트 71개, 실제 MCP 표준입출력, 훅 입출력, 별도 환경에 설치한 패키지의 CSV 예제 실행을 확인했습니다. 스킬 200개 비교의 92.41%는 합성 데이터의 스킬 관련 UTF-8 바이트 감소이며, 실제 모델 토큰·총비용·속도 개선율이 아닙니다. 작은 라이브러리는 오히려 부하가 늘 수 있습니다.

실제 Jev 호출, 각 하네스의 실제 실행, 운영체제 키체인, Remotion 렌더링, GitHub 저장소 생성·푸시·업로드는 검증 또는 완료하지 못했습니다. 제공 영상은 별도로 렌더링한 Pillow + FFmpeg 미리보기이며 화면에도 이를 표시합니다.

## Work continuation — 2026-09-22

This section supersedes the earlier build-environment limitations where stated.

- Host: Linux, Python 3.12.14, Node.js 24.19.0.
- Fresh virtual environment: `pip install ".[dev,secure]"` succeeded with registry-downloaded dependencies.
- Test suite: **71 passed in 2.59 seconds**. MCP stdio and hook subprocess checks are included.
- Guided installer: `Install.py --offline --non-interactive --client none --no-keychain` completed in a separate temporary application directory. It created a runtime, copied six bundled skills, wrote its launcher, and passed its non-live doctor check. No user host configuration or native skills were changed.
- The synthetic benchmark reproduced all committed counts and hashes, including 58,004 versus 4,403 bytes for 200 skills.
- Remotion: `npm install` and dependency-backed `npm run typecheck` succeeded. The new `video/package-lock.json` resolves packages from the public npm registry. Rendering failed before producing output because downloading Chrome Headless Shell returned `ERR_PROXY_TUNNEL`. Existing EN/KO preview MP4s remain the separate Pillow/FFmpeg outputs.
- The manual video workflow now uses `npm ci` and installs a Korean-capable system font. The Python workflow also covers installer and example changes.
- GitHub: the connector confirms the `himomohi` account and returned 404 for `himomohi/jev-skill-router`. The connector lacks repository creation. The browser's secure sign-in attempt returned an incorrect-credentials error; repository creation, push, release and Actions execution are still pending authenticated browser access.
- TypeSafe API request/response definitions and the official skill-suggestion cookbook were rechecked. No live API key was present, so no paid Jev request or live-quality claim was made.

한국어: Work에서 신규 의존성 설치, 전용 설치 프로그램, 테스트 71개, 실제 의존성을 사용한 TypeScript 검사까지 추가로 확인했습니다. 영상 렌더링은 브라우저 다운로드 연결 오류로 중단됐으며 GitHub 게시에는 웹 로그인 완료가 필요합니다.
