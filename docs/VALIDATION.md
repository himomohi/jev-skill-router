# Validation record — 2026-09-22

Version **0.4.1**. This records engineering checks and measured scope; it is not production certification, a self-certified 90/100 score or a live Jev quality claim.

## Current local results

- **289 tests passed, 2 Windows-only tests skipped**, Linux / Python 3.12.14. The official MCP SDK test ran rather than skipping. Provider unit-test responses remain fixtures.
- Cancellation checks cover active and queued HTTP, retry waits, streamed responses, pre-cancelled routes, responsive ping, continued routing after cancellation, bounded queues, EOF cleanup and no caching of cancelled results.
- Retrieval checks cover default full-catalog behavior, smaller catalogs, Unicode/CJK normalization, excluded body-only terms, cutoff ties, metadata edit invalidation, API-free empty retrieval, verification gates, ephemeral CLI overrides and the 4,096-skill budget boundary.
- Upgrade checks cover preserved configuration, mode, roots, client registration and launchers, mismatched installed versions and idempotent/conflicting host registration. Actual isolated upgrade evidence is recorded separately below.
- Release checks cover trusted-event gating, version drift, immutable tags/assets, partial draft recovery, mismatched bytes, network/authentication failures and deterministic ZIP/tar timestamps. `build_release.py check` passes for 0.4.1.
- Existing regression coverage retains safe path/read boundaries, revision-bound pagination, malformed MCP/provider responses, shared request/deadline budgets, accounting, catalog cache invalidation, sharding, confidence/fit gates and no silent offline fallback.

## Actual protocol and host connection checks

| Check | Environment | Result | Scope |
| --- | --- | --- | --- |
| Official MCP Python SDK | 1.30.0, Python 3.12.14 | Passed | Real stdio initialize/list/route; four-page UTF-8/CRLF reconstruction; digest/traversal rejection; ping/cache reuse |
| Codex CLI | 0.155.1, Linux | Passed | Disposable-profile registration, unchanged repeated registration, Codex app-server MCP discovery |
| Claude Code | 2.1.278, Linux | Passed | Disposable-profile registration, unchanged repeated registration, actual MCP Connected status |

[SDK raw report](mcp-sdk-report.json) · [Host connection raw report](host-connection-report.json). No API/model request was made. The direct route subprocess check in the host script is separate from the host connection: neither is evidence that a host model used a skill successfully.

## Evaluation and scale

- [96 original EN/KO challenge cases](COMPARATIVE_EVALUATION.md): 48 cases per language, direct requests, paraphrases, near misses, no-match and multi-skill tasks. All pass local dataset/preflight checks without credentials. Labels are project-authored and correlated, not independently held out.
- [Local comparison report](comparison-report.json): independent BM25 top-1 60/96 exact matches; threshold baseline 53/96. **Live Jev was not run.**
- Production retrieval at limit 8 retained 83/92 required candidates (90.22%), with all required skills retained in 75/84 positive cases. This candidate recall is not model accuracy. Nine positive cases lose a required skill.
- [Synthetic scale report](scaling-benchmark.json): full-catalog base request bounds are 4/7/28/58 for 200/500/2,000/4,096 skills. Indexed limit 64 gives 2 in all four scenarios. The default 32-attempt cap blocks the 58-request plan before spending. These are bounds, not live latency/cost observations.
- [Context accounting](benchmark.json): 200 synthetic skills use 58,088 → 4,940 UTF-8 bytes (91.50% reduction). Five skills increase modeled context by 27.28%. This is one skill-related context with the same selected body, not total conversation tokens or savings.

Host connection reports above were captured for 0.4.0; the 0.4.1 patch changes publishing logic and package version, with the same routing/host integration code.

## Actual upgrade check

An isolated guided installation of 0.3.0 was upgraded using the new `Install.py --upgrade --non-interactive --no-keychain`. The installation succeeded, config bytes were unchanged, offline mode and all six example skills remained, and the bound launcher returned `jev-skills 0.4.0`. [Raw result](upgrade-report.json). No model/API request or real keychain access occurred.

## Cross-platform CI and release

The updated Tests workflow requires Ubuntu Python 3.11/3.13, macOS Python 3.12 and Windows Python 3.12, includes the official MCP SDK check, and gates version metadata. The Release workflow accepts only a successful main push's exact tested SHA. [v0.4.0 CI run 35753374736](https://github.com/himomohi/jev-skill-router/actions/runs/35753374736) passed all four jobs for `757ffdf`: Windows 286 passed; other jobs 284 passed with two Windows-only skips. The release uploaded all four assets but remained a draft because the published-tag endpoint cannot find drafts. Version 0.4.1 adds authenticated draft discovery, fresh numeric-ID lookup and five regression cases.

**v0.4.1 passed and was published.** [Tests run 35753979087](https://github.com/himomohi/jev-skill-router/actions/runs/35753979087) verified commit [`f72e87e`](https://github.com/himomohi/jev-skill-router/commit/f72e87e2890593653768c580a6258cbed209e912):

| Environment | Test result |
| --- | --- |
| Ubuntu / Python 3.11 | 289 passed, 2 Windows-only skipped |
| Ubuntu / Python 3.13 | 289 passed, 2 Windows-only skipped |
| macOS / Python 3.12 | 289 passed, 2 Windows-only skipped |
| Windows / Python 3.12 | 291 passed |

[Release run 35754099365](https://github.com/himomohi/jev-skill-router/actions/runs/35754099365) succeeded. [v0.4.1](https://github.com/himomohi/jev-skill-router/releases/tag/v0.4.1) is published and marked latest, with its tag pointing to that exact tested commit. The wheel, sdist, source ZIP and SHA256SUMS were uploaded and downloaded for byte verification before the draft was published. The subsequent main commit updates only this validation record; release assets retain the tested snapshot.


Historical [v0.3.0 CI run 35737405992](https://github.com/himomohi/jev-skill-router/actions/runs/35737405992) passed for [`f1e0607`](https://github.com/himomohi/jev-skill-router/commit/f1e0607d98ccacf700e198ce71e75bc27c60179e): Windows 201 passed; the other three jobs 199 passed with two Windows-only skips. These earlier results do not substitute for the current version's CI.

Historical v0.2.1 [local refresh measurement](runtime-benchmark.json): 200 synthetic files, five alternating runs per mode on Linux; median full refresh 147.313 ms versus incremental 21.975 ms, unchanged file reloads 200 → 0. This is local traversal/parsing, not model or whole-task speed.

## Remaining external verification

- Live Jev authentication and selection quality, including Korean; inference latency and actual billed cost. No live key was available in this development environment.
- Native-versus-routed model task completion under identical conditions. CLI connection checks are insufficient evidence for this claim.
- Cursor UI integration and actual macOS Keychain, Windows Credential Manager or Linux Secret Service behavior.
- Long-running production workloads and independently adjudicated holdout cases. [Quality gates](QUALITY.md).

## Reproduce

```bash
python -m pip install -e '.[dev,protocol]'
python -m pytest -q
python scripts/build_release.py check
python scripts/benchmark_context.py
python scripts/benchmark_scaling.py
python scripts/compare_routing.py --preflight
python scripts/check_mcp_client.py
python scripts/check_host.py --client codex
python scripts/check_host.py --client claude
```

The host checks require the corresponding actual CLI on PATH and use disposable profiles. Live evaluation requires secure local credential setup and explicit `--allow-live`; it can incur API charges. Reports without a live run must not be presented as live performance evidence.

## 한국어 요약

로컬은 289개 통과·Windows 전용 2개 제외입니다. Windows CI에서는 전용 테스트를 포함한 291개 전부 통과했습니다. Ubuntu 두 환경과 macOS도 각각 289개 통과·Windows 전용 2개 제외로 완료했습니다. 0.4.1 릴리스를 테스트 커밋 f72e87e에서 생성하고 게시했으며, 네 다운로드 파일의 바이트와 체크섬도 확인했습니다. 공식 MCP SDK 왕복과 실제 Codex·Claude 등록/연결을 통과했습니다. 요청 취소, 선택형 대규모 검색, 설정 보존 업데이트, 비교 평가 및 버전 일치 배포를 보강했습니다. 96개 자체 작성 사례의 로컬 기준선 결과와 후보 누락도 함께 공개합니다.

실제 Jev 판단·요금·지연, 모델을 사용한 하네스 작업 성공률, Cursor UI와 OS 키체인은 아직 미검증입니다. 이 한계를 숨기고 90점이나 90% 정확도로 표시하지 않습니다.

The first v0.4.0 Windows CI run exposed a newline assumption in the new SDK smoke fixture: text-mode file creation converted LF to CRLF, but its expected string still used LF. The fixture now writes explicit CRLF bytes on every platform and compares every returned page to those exact bytes decoded as UTF-8. Production read behavior was unchanged.
