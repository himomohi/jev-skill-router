# Large catalogs: bounded provider candidates

The default remains `candidate_strategy=all`: every discovered skill can reach Jev's semantic ranking. Version 0.4.0 adds **explicit** metadata retrieval for users willing to trade recall for a smaller provider candidate set.

```bash
jev-skills plan "Inspect specialist operation" --candidate-strategy indexed --candidate-limit 64
```

With more than 64 skills, the local BM25 index narrows names/descriptions to at most 64 candidates. Jev still ranks and verifies them. NFKC normalization and CJK bigrams help literal matching but cannot translate a request. Bodies are excluded from the index. An empty retrieval stops before credentials or API calls; it is not a semantic no-match decision. Smaller catalogs remain complete. Catalog changes invalidate the cached index.

`retrieval` in both planning and route results reports `considered_skills`, `index_applied`, `truncated`, `matched_skills` and excluded cutoff ties when applicable. A returned `no_match` in indexed mode applies only to the evaluated pool. All-catalog mode is available as a per-call override. Filesystem discovery still covers all configured roots.

## Reproduced local request bounds

Run `python scripts/benchmark_scaling.py`. [Raw result](scaling-benchmark.json). The synthetic scenario uses identical 236-character descriptions and short bodies, so ties are deliberate. No credentials or provider requests are used.

| Catalog size | Full-catalog base request upper bound | Indexed, limit 64 | Full catalog fits default 32-request cap |
| ---: | ---: | ---: | --- |
| 200 | 4 | 2 | Yes |
| 500 | 7 | 2 | Yes |
| 2,000 | 28 | 2 | Yes |
| 4,096 | 58 | 2 | No: blocked before spending |

These counts combine ranking and conservative verification slots. They are fresh-route plans, excluding cache savings; retries use the same hard HTTP-attempt cap. Other metadata/body lengths can change the bounds. This table does not measure live latency, billed cost or routing quality.

## Measure the recall tradeoff

The [96-case authored challenge suite](COMPARATIVE_EVALUATION.md) includes a separate production-index retention check with **limit 8** so narrowing actually occurs in its 16-skill catalog. It retained **83 of 92 required skills (90.22%)** and every required skill in **75 of 84 positive cases**. Nine positive cases lost a required skill before Jev could inspect it. No-match cases are excluded from this recall denominator; retrieving a candidate is not selecting it.

This result is a warning against enabling lexical narrowing blindly. It is **not 90.22% Jev accuracy**, an independent holdout result, or a universal recall guarantee. Run the comparison on representative local tasks and consider descriptions in the languages used by your team. Choose `all` if semantic recall across the full catalog is more important than reducing provider candidates.

## 한국어

기본값 `all`은 전체 목록을 Jev가 평가합니다. 명시적으로 `indexed`를 켜면 이름·설명에서 찾은 후보만 Jev에 전달하며, 나머지 스킬은 평가하지 않습니다. 실제 비용·지연시간을 측정한 결과가 아니라 사전 요청 상한입니다. 16개 스킬·96개 자체 작성 사례에서 후보 8개를 남겼을 때 필요한 스킬 92개 중 83개가 남았고, 9개 사례에서는 필요한 후보가 빠졌습니다. 이 값을 Jev 정확도나 제품 점수로 해석하면 안 됩니다.
