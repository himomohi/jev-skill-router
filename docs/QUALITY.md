# Quality and release gates

Version 0.4.0 improves verifiable engineering quality. This checklist does not assign a self-certified 90/100 score: independent users may weigh quality differently, and live model/task evidence is still missing.

| Area | Evidence delivered | Remaining verification |
| --- | --- | --- |
| Reliability | Shared request/time bounds, malformed-input recovery, digest-bound reads, cache invalidation, active/queued cancellation and follow-up reuse tests | Long-running production traffic |
| Scale | Opt-in metadata index, visible scope/ties, full-catalog default, 4,096-skill preflight fixture | Representative large-catalog live recall and latency |
| Interoperability | Official MCP SDK stdio roundtrip; actual Codex/Claude CLI registration and MCP connection | Model-driven host task trials; Cursor UI |
| Installation | Explicit configuration-preserving upgrade, version check, idempotent registration | Actual OS keychain integrations |
| Evaluation | 96 original EN/KO challenge cases, two independent lexical baselines, candidate retention, capped live comparison and caller-scored paired host reports | Live Jev results and independent adjudication |
| Release | Four-platform CI matrix, version/documentation checks, tested-SHA release, immutable assets/checksums, resumable draft | See CI and release links in the validation record |
| Documentation | English/Korean changelogs and update guides, compatibility and migration steps, recorded limitations | Feedback from new users |

## Evidence required before a broad quality claim

1. Freeze an independent task set and acceptance rubric before tuning thresholds. Include English/Korean paraphrases, near misses, no-match and multi-skill cases; keep separate development and evaluation sets.
2. Execute live Jev and both lexical baselines on matching catalog/task fingerprints. Include failed and interrupted cases. Report uncertainty and language/category breakdowns, not only one pooled percentage.
3. Run native and routed host tasks with the same model, tools and inputs in fresh workspaces. Randomize order, repeat trials and score actual final artifacts. Include all host and router usage, errors and retries. Require the routed setup to meet agreed task-success and latency/cost criteria.
4. Verify Cursor UI and supported OS keychains on the actual platforms. Retain sanitized trace evidence and document the client versions.

The repository supplies executable evaluation and smoke-test tooling for these steps. No Jev API key was available in this development environment, and no live paid-model request was made. Connection checks must not be reported as model task completion.

## 한국어

이번 버전은 코드 안정성·대규모 처리·업데이트·검증 도구·배포 재현성을 개선했습니다. 공식 MCP SDK와 실제 Codex/Claude 연결도 확인했습니다. 다만 “누가 봐도 90점”은 자체 점수만으로 증명할 수 없습니다. 실제 Jev 판단 품질, 동일 조건의 하네스 작업 성공률·비용·지연, 독립 평가 데이터와 OS 키체인 검증이 남아 있습니다. 위 표는 완료한 증거와 남은 검증을 공개하는 기준입니다.
