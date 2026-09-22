"""Compare independent local baselines with explicitly requested, capped Jev runs.

The default is offline: no credential lookup or provider request. This measures
skill selection, not main-model quality, end-to-end task success or total bills.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_skill_router.config import Config, RouterError, atomic_json
from jev_skill_router.router import Router

_spec = importlib.util.spec_from_file_location("jev_comparison_live", ROOT / "scripts/evaluate_live.py")
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)

SCHEMA_VERSION = 1
STOP_WORDS = frozenset("a an the this that and or to of for in on with is are be it its as by from me my do does not only then into have has was we our you your".split())
CATEGORIES = {"direct", "paraphrase", "near-miss", "no-match", "multi-skill", "custom"}


def finite_nonnegative(value) -> bool:
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def terms(text: str) -> list[str]:
    """Independent lexical baseline; words plus Hangul bigrams, no translation."""
    words = re.findall(r"[\w]+", unicodedata.normalize("NFKC", text).casefold())
    result = [word for word in words if word not in STOP_WORDS]
    for word in words:
        for hangul in re.findall(r"[가-힣]+", word):
            result.extend("ko:" + hangul[i:i + 2] for i in range(len(hangul) - 1))
    return result


class BM25Baseline:
    """Metadata-only Okapi BM25 implemented independently of production retrieval.

    Constants are fixed before benchmark execution, not calibrated on case labels.
    Corpus input deliberately has no task labels or expected skill sets.
    """
    def __init__(self, skills):
        self.documents = [(skill.name, Counter(terms(skill.name + " " + skill.description)))
                          for skill in sorted(skills, key=lambda skill: skill.name)]
        self.lengths = [sum(counts.values()) for _, counts in self.documents]
        self.average = sum(self.lengths) / max(1, len(self.lengths)) or 1
        self.frequencies = Counter(term for _, counts in self.documents for term in counts)

    def rank(self, task: str, context: str = "") -> list[tuple[str, float, int]]:
        query = set(terms(task + " " + context))
        size = len(self.documents)
        ranking = []
        for (name, counts), length in zip(self.documents, self.lengths):
            matched = query & counts.keys()
            score = 0.0
            for term in sorted(matched):
                frequency = counts[term]
                idf = math.log(1 + (size - self.frequencies[term] + .5) / (self.frequencies[term] + .5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / self.average))
            if score > 0:
                ranking.append((name, score, len(matched)))
        return sorted(ranking, key=lambda row: (-row[1], row[0]))

    def select(self, task: str, context: str = "", *, method: str, max_skills: int) -> list[str]:
        ranking = self.rank(task, context)
        if not ranking:
            return []
        if method == "bm25-top1":
            return [ranking[0][0]]
        if method != "bm25-threshold":
            raise RouterError("Unknown baseline method.")
        return sorted(name for name, score, overlap in ranking[:max_skills]
                      if score >= 4.0 and score >= .72 * ranking[0][1] and overlap >= 2)


def load_cases(path: Path) -> list[dict]:
    cases = live.load_cases(path)
    # live.load_cases already bounds and validates the input and task sizes.
    with path.open("rb") as source:
        raw = source.read(2_000_001)
    if len(raw) > 2_000_000:
        raise RouterError("Dataset exceeds its size limit.")
    rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    if len(rows) != len(cases):
        raise RouterError("Dataset changed while being loaded.")
    seen = set()
    for index, (case, original) in enumerate(zip(cases, rows)):
        if (case["task"] != original.get("task", "").strip()
                or case["context"] != original.get("context", "")
                or case["expected"] != sorted(original.get("expected", []))):
            raise RouterError("Dataset changed while being loaded.")
        identity = original.get("case_id", "case-" + str(index))
        category = original.get("category", "custom")
        if (not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identity)
                or identity in seen or category not in CATEGORIES):
            raise RouterError("Cases need unique simple case_id values and documented categories.")
        seen.add(identity)
        case.update(case_id=identity, category=category)
    return cases


def core_cases(cases: list[dict]) -> list[dict]:
    # Keep compatibility with the privacy-preserving evaluate_live schema.
    return [{field: row[field] for field in ("task", "context", "expected", "language")} for row in cases]


def measure_record(index: int, row: dict, chosen: list[str], seconds: float) -> dict:
    expected = set(row["expected"])
    selected = set(chosen)
    return {"case": index, "language": row["language"], "category": row["category"],
            "status": "selected" if selected else "no_match", "correct": expected == selected,
            "expected_count": len(expected), "selected_count": len(selected),
            "true_positives": len(expected & selected), "false_positives": len(selected - expected),
            "false_negatives": len(expected - selected), "seconds": round(seconds, 6)}


def summarize(records: list[dict], planned: int) -> dict:
    correct = sum(row["correct"] for row in records)
    no_match = [row for row in records if row["expected_count"] == 0]
    summary = {"planned": planned, "attempted": len(records), "unattempted": planned - len(records),
               "errors": sum(row["status"] == "error" for row in records), "correct": correct,
               "exact_match_accuracy_including_errors": correct / len(records) if records else None,
               "no_match_cases_attempted": len(no_match),
               "no_match_false_selections": sum(row["selected_count"] > 0 for row in no_match),
               "required_skill_abstentions": sum(row["expected_count"] > 0 and row["status"] in {"uncertain", "no_match"} for row in records),
               "latency": live.latency([row["seconds"] for row in records])}
    for field in ("language", "category"):
        summary["by_" + field] = {}
        for group in sorted({row[field] for row in records}):
            selected = [row for row in records if row[field] == group]
            summary["by_" + field][group] = {"attempted": len(selected), "correct": sum(row["correct"] for row in selected),
                                            "accuracy": sum(row["correct"] for row in selected) / len(selected)}
    # evaluate_live v3 does not retain selections, so never infer partial-credit
    # recall/precision from only exact-match and set cardinalities.
    if all("true_positives" in row for row in records):
        totals = {field: sum(row[field] for row in records) for field in ("true_positives", "false_positives", "false_negatives")}
        tp, fp, fn = totals.values()
        summary["micro_precision"] = tp / (tp + fp) if tp + fp else None
        summary["micro_recall"] = tp / (tp + fn) if tp + fn else None
        summary.update(totals)
    else:
        summary.update(micro_precision=None, micro_recall=None)
    return summary


def local_baselines(cases: list[dict], skills, max_skills: int) -> dict:
    started = time.perf_counter()
    model = BM25Baseline(skills)
    build_seconds = round(time.perf_counter() - started, 6)
    result = {}
    for method in ("bm25-top1", "bm25-threshold"):
        records = []
        for index, row in enumerate(cases):
            started = time.perf_counter()
            chosen = model.select(row["task"], row["context"], method=method, max_skills=max_skills)
            records.append(measure_record(index, row, chosen, time.perf_counter() - started))
        result[method] = {"kind": "independent_local_lexical_baseline", "executed": True,
                          "http_requests": 0, "model_calls": 0, "index_build_seconds": build_seconds,
                          "parameters": {"k1": 1.2, "b": .75, "max_skills": 1 if method == "bm25-top1" else max_skills,
                                         "min_score": 0 if method == "bm25-top1" else 4.0,
                                         "top_score_ratio": None if method == "bm25-top1" else .72,
                                         "min_matched_terms": 1 if method == "bm25-top1" else 2},
                          "summary": summarize(records, len(cases)), "records": records}
    return result


def validate_live_report(data: dict, setup: dict, cases: list[dict]) -> dict:
    if (not isinstance(data, dict) or data.get("schema_version") != live.SCHEMA_VERSION or data.get("live") is not True
            or any(data.get(key) != setup[key] for key in ("dataset_sha256", "catalog_content_sha256"))
            or data.get("planned_cases") != len(cases)):
        raise RouterError("Live report must match this dataset and catalog, using evaluate_live schema 3.")
    records = data.get("records")
    if not isinstance(records, list) or len(records) > len(cases):
        raise RouterError("Invalid live report records.")
    clean = []
    seen = set()
    for row in records:
        if (not isinstance(row, dict) or type(row.get("case")) is not int or not 0 <= row["case"] < len(cases)
                or row["case"] in seen or type(row.get("correct")) is not bool or row.get("status") not in live.STATUSES
                or not finite_nonnegative(row.get("seconds"))
                or type(row.get("selected_count")) is not int or not 0 <= row["selected_count"] <= 3
                or type(row.get("expected_count")) is not int or row["expected_count"] != len(cases[row["case"]]["expected"])
                or (row["status"] == "error" and row["correct"])
                or (row["correct"] and row["expected_count"] != row["selected_count"])
                or (row["status"] in {"no_match", "uncertain", "empty_catalog"} and row["selected_count"] != 0)):
            raise RouterError("Invalid live report record.")
        seen.add(row["case"])
        item = {field: row[field] for field in ("case", "status", "correct", "seconds", "selected_count", "expected_count")}
        item.update(language=cases[row["case"]]["language"], category=cases[row["case"]]["category"])
        clean.append(item)
    requests = data.get("requests")
    if not isinstance(requests, dict) or any(type(requests.get(field)) is not int or requests[field] < 0 for field in live.COUNTERS):
        raise RouterError("Invalid live request accounting.")
    complete = len(clean) == len(cases) and all(row["status"] != "error" for row in clean)
    config = data.get("configuration", {})
    if not isinstance(config, dict):
        raise RouterError("Invalid live configuration.")
    # Import only documented metadata. Raw task/provider/error/config paths are
    # never copied out of an imported report into a distributable report.
    safe_configuration = {key: live.safe_setting(key, value) for key, value in config.items()
                          if key in Config.__dataclass_fields__ and key != "roots"}
    strategy = config.get("candidate_strategy", "all")
    if strategy not in {"all", "indexed"}:
        raise RouterError("Invalid live candidate strategy.")
    safe_configuration["candidate_strategy"] = strategy
    return {"kind": "jev_live_routing", "executed": True, "configuration": safe_configuration,
            "completed_cold_dataset": complete, "summary": summarize(clean, len(cases)), "records": clean,
            "requests": {field: requests[field] for field in live.COUNTERS},
            "billed_cost_usd": None, "estimated_jev_cost_usd": data.get("estimated_jev_cost_usd")
            if finite_nonnegative(data.get("estimated_jev_cost_usd")) else None}


def paired_comparisons(methods: dict) -> list[dict]:
    pairs = []
    names = list(methods)
    for i, left_name in enumerate(names):
        for right_name in names[i + 1:]:
            left = {row["case"]: row for row in methods[left_name]["records"]}
            right = {row["case"]: row for row in methods[right_name]["records"]}
            shared = sorted(left.keys() & right.keys())
            a = sum(left[index]["correct"] for index in shared)
            b = sum(right[index]["correct"] for index in shared)
            pairs.append({"left": left_name, "right": right_name, "paired_cases": len(shared),
                          "left_correct": a, "right_correct": b,
                          "right_minus_left_accuracy_points": 100 * (b - a) / len(shared) if shared else None,
                          "left_only_correct": sum(left[index]["correct"] and not right[index]["correct"] for index in shared),
                          "right_only_correct": sum(right[index]["correct"] and not left[index]["correct"] for index in shared)})
    return pairs


def import_host_results(path: Path, setup: dict, cases: list[dict]) -> dict:
    """Summarize caller-scored native/routed host trials without claiming we ran them."""
    data = live.read_json(path, 2_000_000)
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or any(data.get(key) != setup[key] for key in ("dataset_sha256", "catalog_content_sha256"))
            or not isinstance(data.get("records"), list) or len(data["records"]) > 2 * len(cases)):
        raise RouterError("Host results must identify this dataset/catalog and contain bounded paired records.")
    indexed = {"native": {}, "routed": {}}
    for row in data["records"]:
        if (not isinstance(row, dict) or row.get("strategy") not in ("native", "routed")
                or type(row.get("case")) is not int or not 0 <= row["case"] < len(cases)
                or row["case"] in indexed[row["strategy"]] or type(row.get("task_success")) is not bool):
            raise RouterError("Invalid or duplicate host result record.")
        seconds = row.get("seconds")
        if not finite_nonnegative(seconds):
            raise RouterError("Host duration must be a finite nonnegative number.")
        clean = {"task_success": row["task_success"], "seconds": seconds}
        for key in ("input_tokens", "output_tokens", "reported_cost_usd"):
            value = row.get(key)
            allowed = (int, float) if key == "reported_cost_usd" else (int,)
            if value is not None and (type(value) not in allowed or not finite_nonnegative(value)):
                raise RouterError("Host usage and cost must be null or finite nonnegative numbers.")
            clean[key] = value
        indexed[row["strategy"]][row["case"]] = clean
    paired = sorted(indexed["native"].keys() & indexed["routed"].keys())
    if not paired:
        raise RouterError("Host results need at least one native/routed case pair.")
    summaries = {}
    for strategy, rows in indexed.items():
        group = [rows[index] for index in paired]
        summary = {"paired_cases": len(paired), "unpaired_records_excluded": len(rows) - len(paired),
                   "producer_reported_success_rate": sum(row["task_success"] for row in group) / len(group),
                   "completion_latency": live.latency([row["seconds"] for row in group]), "verified_billed_cost_usd": None}
        for key in ("input_tokens", "output_tokens", "reported_cost_usd"):
            known = [row[key] for row in group if row[key] is not None]
            summary[key + "_reported_cases"] = len(known)
            summary[key + "_total"] = sum(known) if len(known) == len(group) else None
        summaries[strategy] = summary
    return {"performed": False, "imported": True, "paired_cases": len(paired),
            "provenance": "Caller-supplied, caller-scored host trials; this process did not execute or independently verify them.",
            "strategies": summaries,
            "limitations": ["Identity checks pair the same task/catalog but do not verify host/model settings, tool access, evaluator quality or authenticity.",
                            "Missing token/cost observations stay unknown; reported cost is not a verified invoice."]}


def retrieval_coverage(cases, skills, limit):
    """Candidate recall only: retention is necessary, never sufficient for selection."""
    from jev_skill_router.retrieval import MetadataIndex
    skills = list(skills)
    index = MetadataIndex(skills)
    names = {skill.id: skill.name for skill in skills}
    applied = len(skills) > limit
    records = []
    for number, row in enumerate(cases):
        ids = index.search(row['task'] + '\n' + row['context'], limit).ids if applied else tuple(names)
        expected = set(row['expected'])
        retained = expected & {names[sid] for sid in ids}
        records.append({'case': number, 'language': row['language'], 'expected_count': len(expected),
                        'retained_count': len(retained), 'candidate_count': len(ids),
                        'all_required_retained': expected <= {names[sid] for sid in ids}})
    required = [row for row in records if row['expected_count']]
    total = sum(row['expected_count'] for row in required)
    return {'candidate_limit': limit, 'index_applied': applied,
            'required_cases': len(required),
            'all_required_retained': sum(row['all_required_retained'] for row in required),
            'required_skills': total, 'retained_required_skills': sum(row['retained_count'] for row in required),
            'micro_recall': sum(row['retained_count'] for row in required) / total if total else None,
            'scope': 'Local candidate retention, not Jev selection accuracy or no-match correctness.',
            'records': records}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", type=Path, default=ROOT / "examples/comparison/cases.jsonl")
    parser.add_argument("--config", type=Path, help="Custom catalog configuration; default is the 16 authored comparison skills.")
    parser.add_argument("--allow-live", action="store_true", help="Authorize billed Jev routing requests and sending task/catalog evidence to TypeSafe.")
    parser.add_argument("--preflight", action="store_true", help="Run local baselines only, even when --allow-live is present.")
    parser.add_argument("--strategy", choices=["all", "indexed", "both"], default="all")
    parser.add_argument("--candidate-limit", type=int, default=8, help="Comparison indexed pool, 8–512 (default 8 exercises narrowing on the 16-skill suite; production default is 64).")
    parser.add_argument("--max-requests", type=int, default=256, help="Total transport-attempt cap shared by all live strategies, including retries (1–1000).")
    parser.add_argument("--jev-report", type=Path, action="append", default=[], help="Import an evaluate_live v3 report with matching task/catalog fingerprints.")
    parser.add_argument("--host-results", type=Path, help="Import explicitly caller-scored native/routed end-to-end trials; never claimed as executed here.")
    parser.add_argument("--rates", type=Path, help="Explicit exact-model rates for live estimates; no assumed prices.")
    parser.add_argument("--out", type=Path, help="Optional report file; stdout always contains the summary.")
    args = parser.parse_args(argv)
    if not 1 <= args.max_requests <= 1000:
        parser.error("--max-requests must be 1–1000.")
    if not 8 <= args.candidate_limit <= 512:
        parser.error("--candidate-limit must be 8–512.")
    try:
        cases = load_cases(args.dataset)
        core = core_cases(cases)
        config = Config.load(args.config) if args.config else Config(roots=[str(ROOT / "examples/comparison/skills")], max_skills=3, retries=0)
        config = replace(config, candidate_limit=args.candidate_limit)
        router = Router(config)
        try:
            setup = live.preflight(core, router, args.max_requests)
            if any(len(row["expected"]) > config.max_skills for row in cases):
                raise RouterError("max_skills must accommodate the largest expected set for this comparison.")
            methods = local_baselines(cases, router.catalog.skills.values(), config.max_skills)
            coverage = retrieval_coverage(cases, router.catalog.skills.values(), args.candidate_limit)
            plans = []
            for row in cases:
                try:
                    plans.append(router.plan(row["task"], row["context"]))
                except RouterError:
                    # A local index miss is a failed preflight, not a reason to
                    # prevent free independent baseline measurement.
                    plans.append({"ready": False})
        finally:
            router.close()
        for index, path in enumerate(args.jev_report):
            method = validate_live_report(live.read_json(path, 8_000_000), setup, cases)
            method["provenance"] = "Imported evaluator output; scoring is producer-reported, not independently re-scored."
            methods["jev-import-" + str(index + 1)] = method
        host_evaluation = import_host_results(args.host_results, setup, cases) if args.host_results else {
            "performed": False, "imported": False, "success_rate": None, "total_cost_usd": None, "completion_seconds": None}
        should_run = args.allow_live and not args.preflight
        total_requests = 0
        full_run = True
        if should_run:
            rates = live.load_rates(args.rates)
            strategies = ["all", "indexed"] if args.strategy == "both" else [args.strategy]
            if "candidate_strategy" not in Config.__dataclass_fields__ and strategies != ["all"]:
                raise RouterError("This checkout does not support indexed routing.")
            key = live.api_key()
            for strategy in strategies:
                remaining = args.max_requests - total_requests
                if remaining <= 0:
                    full_run = False
                    break
                selected_config = replace(config, mode="live", **({"candidate_strategy": strategy} if "candidate_strategy" in Config.__dataclass_fields__ else {}))
                client = live.JevClient(selected_config, key, max_requests=remaining)
                result = live.evaluate(selected_config, core, client, max_requests=remaining, rates=rates)
                method = validate_live_report(result, setup, cases)
                method["provenance"] = "Executed by this process through evaluate_live; no desktop host involved."
                methods["jev-" + strategy] = method
                total_requests += result["requests"]["http_requests"]
                full_run = full_run and result["completed_full_dataset"]
                if not result["completed_full_dataset"]:
                    break
        report = {"schema_version": SCHEMA_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
                  "dataset_sha256": setup["dataset_sha256"], "catalog_content_sha256": setup["catalog_content_sha256"],
                  "catalog_size": setup["catalog_size"], "planned_cases": len(cases),
                  "dataset_provenance": "Bundled: original project-authored challenge cases, correlated EN/KO pairs, not independently held out. Custom inputs: provenance supplied by caller.",
                  "live_performed_this_run": should_run, "credentials_read": should_run,
                  "http_requests_this_run": total_requests, "max_http_requests_including_retries": args.max_requests,
                  "routing_preflight": {"cases_ready": sum(plan["ready"] for plan in plans), "cases": len(plans)},
                  "methods": methods, "paired_comparisons": paired_comparisons(methods),
                  "candidate_retrieval": coverage,
                  "host_task_evaluation": host_evaluation,
                  "limitations": [
                      "This is skill-selection evaluation, not a native main-model or end-to-end task comparison.",
                      "Bundled labels and skill descriptions are authored together; no human adjudication or independent held-out workload is claimed.",
                      "Lexical baselines share only the catalog and tasks with Jev; baseline constants are fixed and never tuned from expected labels.",
                      "BM25 top1 cannot select multiple skills; threshold BM25 can select up to the configured max_skills.",
                      "Baseline latency is metadata scoring only; Jev latency includes catalog checks, network and selected-content loading. Do not treat their difference as task time saved.",
                      "Imported live scores are producer-reported. Input identity checks do not prove provider authenticity or billing accuracy.",
                      "Errors count as wrong among attempted cases. Early termination and nonindependent EN/KO families limit generalization.",
                      "No live execution means no Jev accuracy, cost, latency or comparative performance claim is available."]}
        if should_run:
            report = live.redact_strings(report, key)
        destination = args.out
        if destination is None and should_run:
            destination = ROOT / "jev-local-results" / (datetime.now(timezone.utc).strftime("comparison-%Y%m%d-%H%M%S-%f") + ".json")
            destination.parent.mkdir(parents=True, exist_ok=True)
            (destination.parent / ".gitignore").write_text("*\n", encoding="utf-8")
        if destination:
            atomic_json(destination, report)
        print(json.dumps({key: value for key, value in report.items() if key != "methods"} | {
            "report_saved": destination is not None,
            "candidate_retrieval": {key: value for key, value in coverage.items() if key != "records"},
            "methods": {name: {key: value for key, value in method.items() if key != "records"} for name, method in methods.items()}}, indent=2))
        return 0 if full_run else 1
    except (RouterError, OSError, ValueError, TypeError, KeyError, OverflowError):
        print("Comparison could not complete. Check the bounded dataset, configuration or report locally; sensitive details are not printed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
