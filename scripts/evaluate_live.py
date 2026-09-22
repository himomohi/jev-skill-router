"""Preflight or explicitly opt in to a bounded, real Jev routing evaluation.

No credentials are read and no API calls are made without --allow-live.
Reports omit task text, skill names/bodies, local paths and credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_skill_router.config import Config, RouterError, api_key, atomic_json
from jev_skill_router.jev import JevClient, encoded
from jev_skill_router.mcp import BOOTSTRAP, TOOL
from jev_skill_router.router import Router

SCHEMA_VERSION = 3
STATUSES = {"selected", "uncertain", "no_match", "empty_catalog", "error"}
COUNTERS = ("api_calls", "http_requests", "retry_requests", "request_bytes",
            "input_tokens", "output_tokens", "unreported_requests")


def read_json(path: Path, max_bytes: int = 2_000_000):
    """Bound inputs before parsing and keep filenames/content out of errors."""
    try:
        with path.open("rb") as source:
            raw = source.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError()
        return json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RouterError("Cannot read a valid, bounded JSON input.") from exc


def load_cases(path: Path) -> list[dict]:
    try:
        with path.open("rb") as source:
            raw = source.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError()
        rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
        if not 1 <= len(rows) <= 200:
            raise ValueError()
        cases = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError()
            task, context, expected = row.get("task"), row.get("context", ""), row.get("expected")
            language = row.get("language", "ko" if isinstance(task, str) and re.search(r"[가-힣]", task) else "en")
            if (not isinstance(task, str) or not task.strip() or not isinstance(context, str)
                    or not isinstance(expected, list) or not all(isinstance(x, str) and x for x in expected)
                    or len(expected) != len(set(expected)) or language not in {"en", "ko", "other"}
                    or len(encoded({"task": task.strip(), "recent_context": context})) > 6000):
                raise ValueError()
            cases.append({"task": task.strip(), "context": context, "expected": sorted(expected), "language": language})
        return cases
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise RouterError("Dataset needs 1–200 valid JSONL cases: task, expected:string[], optional context and language (en/ko/other).") from exc


def load_rates(path: Path | None) -> dict | None:
    if path is None:
        return None
    data = read_json(path, 4096)
    if not isinstance(data, dict) or not isinstance(data.get("model"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", data["model"]):
        raise RouterError("Rates need one exact model ID and USD per million input/output tokens.")
    rates = {"model": data["model"]}
    for field in ("input_usd_per_million", "output_usd_per_million"):
        value = data.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise RouterError("Rates must be finite nonnegative numbers.")
        rates[field] = value
    return rates


def percentile(values: list[float], fraction: float) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def latency(values: list[float]) -> dict:
    return {"samples": len(values), "p50_seconds": statistics.median(values) if values else None,
            "p95_seconds": percentile(values, .95)}


def summarize(records: list[dict], planned: int, planned_by_language: dict | None = None) -> dict:
    completed = [row for row in records if row["status"] != "error"]
    no_match = [row for row in records if row["expected_count"] == 0]
    wanted = [row for row in records if row["expected_count"] > 0]
    correct = sum(row["correct"] for row in records)
    result = {
        "planned": planned, "attempted": len(records), "completed": len(completed),
        "unattempted": planned - len(records), "errors": len(records) - len(completed),
        "correct": correct,
        "exact_match_accuracy_including_errors": correct / len(records) if records else None,
        "exact_match_accuracy_completed_only": correct / len(completed) if completed else None,
        "no_match_cases_attempted": len(no_match),
        "no_match_correct": sum(row["correct"] for row in no_match),
        "no_match_false_selections": sum(row["selected_count"] > 0 for row in no_match),
        "required_skill_cases_attempted": len(wanted),
        "required_skill_abstentions": sum(row["status"] in {"no_match", "uncertain"} for row in wanted),
        "uncertain": sum(row["status"] == "uncertain" for row in records),
        "cold_all_attempts": latency([row["seconds"] for row in records]),
        "cold_completed": latency([row["seconds"] for row in completed]),
        "warm_all_attempts": latency([row["warm"]["seconds"] for row in records if "warm" in row]),
        "warm_errors": sum(bool(row.get("warm", {}).get("error")) for row in records),
        "warm_cache": latency([row["warm"]["seconds"] for row in records if row.get("warm", {}).get("cache_hit")]),
    }
    groups = {}
    for language in ("en", "ko", "other"):
        group = [row for row in records if row["language"] == language]
        count = (planned_by_language or {}).get(language)
        if group or count:
            groups[language] = {"planned": count, "attempted": len(group), "errors": sum(row["status"] == "error" for row in group),
                                "exact_match_accuracy_including_errors": sum(row["correct"] for row in group) / len(group) if group else None}
    result["by_language"] = groups
    measured = [row["content"] for row in completed if "content" in row]
    native = sum(row["modeled_native_bytes"] for row in measured)
    routed = sum(row["measured_router_envelope_bytes"] for row in measured)
    result["skill_content_accounting"] = {"cases": len(measured), "modeled_native_bytes": native,
                                          "measured_router_envelope_bytes": routed,
                                          "reduction_percent": 100 * (1 - routed / native) if native else None}
    return result


def fingerprints(cases: list[dict], router: Router) -> dict:
    # Content identity is independent of machine-specific absolute directories.
    skills = sorted((s.name, s.description, s.body) for s in router.catalog.skills.values())
    return {"dataset_sha256": hashlib.sha256(encoded(cases)).hexdigest(),
            "catalog_content_sha256": hashlib.sha256(encoded(skills)).hexdigest()}


def preflight(cases: list[dict], router: Router, max_requests: int) -> dict:
    names = [skill.name for skill in router.catalog.skills.values()]
    if not names or len(names) != len(set(names)):
        raise RouterError("Evaluation needs a nonempty catalog with unique skill names.")
    if any(not set(row["expected"]) <= set(names) for row in cases):
        raise RouterError("An expected skill is absent from this catalog.")
    if router.catalog.warnings:
        raise RouterError("Catalog has unreadable or invalid skills; inspect it locally before evaluation.")
    return {"schema_version": SCHEMA_VERSION, "live": False, "mode": "preflight",
            "cases": len(cases), "catalog_size": len(names), "api_requests": 0, "credentials_read": False,
            "cases_by_language": {language: sum(row["language"] == language for row in cases) for language in ("en", "ko", "other")},
            "expected_no_match_cases": sum(not row["expected"] for row in cases),
            "max_http_requests_including_retries": max_requests, **fingerprints(cases, router)}


def content_bytes(router: Router, row: dict, result: dict) -> dict:
    roster = [{"name": skill.name, "description": skill.description} for skill in router.catalog.skills.values()]
    # Same actual selected skill content on both sides. Only the native metadata
    # envelope is modeled; this does not execute or bill a main-model request.
    selected = [{key: value for key, value in entry.items() if key not in {"fit", "score", "confidence"}}
                for entry in result["selected"]]
    native = encoded({"task": row["task"], "recent_context": row["context"], "available_skills": roster, "selected": selected})
    routed = (encoded({"instructions": BOOTSTRAP, "tools": [TOOL]})
              + encoded({"tool": "skill_router", "arguments": {"action": "route", "task": row["task"], "context": row["context"]}})
              + encoded(result))
    return {"modeled_native_bytes": len(native), "measured_router_envelope_bytes": len(routed),
            "reduction_percent": round(100 * (1 - len(routed) / len(native)), 3)}


def metric_delta(after: dict, before: dict) -> dict:
    return {field: after[field] - before[field] for field in COUNTERS}


def safe_setting(field: str, value):
    if type(value) in (int, float) and math.isfinite(value):
        return value
    if isinstance(value, str) and ((field == "model" and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value))
                                   or (field == "mode" and value in {"live", "offline"})):
        return value
    return "[unavailable]"


def redact_strings(value, secret: str):
    """Redact string values without accidentally corrupting JSON booleans/numbers."""
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, dict):
        return {key: redact_strings(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_strings(item, secret) for item in value]
    return value


def error_category(error: RouterError) -> str:
    message = str(error)
    status = re.search(r"\bHTTP (\d{3})\b", message)
    if status:
        return "http_" + status[1]
    for needle, category in (("budget", "request_budget"), ("deadline", "route_deadline"),
                              ("timed out", "network_or_timeout"), ("connection", "network_or_timeout")):
        if needle in message.lower():
            return category
    return "routing_error"


def compare_report(path: Path | None, report: dict) -> dict | None:
    if path is None:
        return None
    previous = read_json(path)
    if (not isinstance(previous, dict) or previous.get("schema_version") != SCHEMA_VERSION
            or previous.get("live") is not True
            or any(previous.get(field) != report[field] for field in ("dataset_sha256", "catalog_content_sha256"))):
        raise RouterError("Comparison requires a live report with the same schema, dataset and catalog content.")
    old_rows = previous.get("records")
    if not isinstance(old_rows, list) or len(old_rows) > 200:
        raise RouterError("Invalid comparison records.")
    indexed = {}
    for row in old_rows:
        if (not isinstance(row, dict) or type(row.get("case")) is not int or not 0 <= row["case"] < report["planned_cases"]
                or row["case"] in indexed or type(row.get("correct")) is not bool
                or row.get("status") not in STATUSES or type(row.get("seconds")) not in (int, float)
                or not math.isfinite(row["seconds"]) or row["seconds"] < 0):
            raise RouterError("Invalid comparison records.")
        indexed[row["case"]] = row
    pairs = [(indexed[row["case"]], row) for row in report["records"] if row["case"] in indexed]
    old_correct = sum(old["correct"] for old, _ in pairs)
    new_correct = sum(new["correct"] for _, new in pairs)
    old_config = previous.get("configuration")
    old_config = old_config if isinstance(old_config, dict) else {}
    changes = {field: {"previous": safe_setting(field, old_config.get(field)), "current": safe_setting(field, value)}
               for field, value in report["configuration"].items() if old_config.get(field) != value}
    old_models = previous.get("models")
    old_models = sorted({model for model in old_models if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", model)}) if isinstance(old_models, list) else []
    return {"scope": "Paired routing results from separate runs, not main-model or final-task performance.",
            "paired_cases": len(pairs), "configuration_equal": not changes, "configuration_changes": changes,
            "previous_models": old_models, "current_models": report.get("models", []),
            "previous_correct": old_correct, "current_correct": new_correct,
            "accuracy_change_percentage_points": 100 * (new_correct - old_correct) / len(pairs) if pairs else None,
            "previous_cold_all_attempts": latency([old["seconds"] for old, _ in pairs]),
            "current_cold_all_attempts": latency([new["seconds"] for _, new in pairs])}


def evaluate(config: Config, cases: list[dict], client: JevClient, *, max_requests: int,
             rates: dict | None = None) -> dict:
    """Run measured requests with a caller-supplied client; mock only in tests."""
    config = replace(config, mode="live", cache_seconds=600)
    router = Router(config, client)
    try:
        setup = preflight(cases, router, max_requests)
    except BaseException:
        router.close()
        raise
    records, models = [], set()
    interrupted = False
    try:
        for index, row in enumerate(cases):
            router.cache.clear()  # No duplicate dataset row can become a cold cache hit.
            before = client.metrics_snapshot()
            record = {"case": index, "language": row["language"], "expected_count": len(row["expected"]),
                      "selected_count": 0, "correct": False}
            try:
                started = time.perf_counter()
                try:
                    result = router.route(row["task"], row["context"])
                finally:
                    record["seconds"] = round(time.perf_counter() - started, 6)
                chosen = sorted(entry["name"] for entry in result["selected"])
                record.update(status=result["status"], selected_count=len(chosen), correct=chosen == row["expected"],
                              cache_hit=result.get("cache_hit", False), content=content_bytes(router, row, result))
                models.update(result.get("models", []))
            except (RouterError, KeyboardInterrupt) as error:
                record["status"] = "error"
                interrupted = isinstance(error, KeyboardInterrupt)
                record["error_category"] = "interrupted" if interrupted else error_category(error)
            record.update(metric_delta(client.metrics_snapshot(), before))
            if record["status"] != "error":
                before_warm = client.metrics_snapshot()
                try:
                    started = time.perf_counter()
                    try:
                        warm = router.route(row["task"], row["context"])
                    finally:
                        warm_seconds = round(time.perf_counter() - started, 6)
                    record["warm"] = {"seconds": warm_seconds,
                                      "cache_hit": warm.get("cache_hit", False),
                                      "same_selection": sorted(entry["name"] for entry in warm["selected"]) == chosen,
                                      **metric_delta(client.metrics_snapshot(), before_warm)}
                except (RouterError, KeyboardInterrupt) as error:
                    interrupted = isinstance(error, KeyboardInterrupt)
                    record["warm"] = {"seconds": warm_seconds, "cache_hit": False,
                                      "error": True, "error_category": "interrupted" if interrupted else error_category(error),
                                      **metric_delta(client.metrics_snapshot(), before_warm)}
            records.append(record)
            if record["status"] == "error" or record.get("warm", {}).get("error"):
                break  # Avoid spending the remaining budget on a persistent auth/provider failure.
    except KeyboardInterrupt:
        interrupted = True
    finally:
        router.close()
    snapshot = client.metrics_snapshot()
    metrics = {field: snapshot[field] for field in COUNTERS}
    metrics["usage_complete"] = metrics["http_requests"] > 0 and metrics["unreported_requests"] == 0
    configuration = asdict(config)
    configuration.pop("roots")
    # Model IDs are metadata, but arbitrary configuration strings may contain paths.
    configuration["model"] = config.model if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", config.model) else "[nonstandard model ID]"
    cold_complete = len(records) == len(cases) and all(row["status"] != "error" for row in records)
    warm_checks_passed = cold_complete and all(
        row.get("warm", {}).get("cache_hit") and row["warm"].get("same_selection")
        and row["warm"].get("http_requests") == 0 and not row["warm"].get("error") for row in records)
    report = {"schema_version": SCHEMA_VERSION, "live": True, "created_utc": datetime.now(timezone.utc).isoformat(),
              "dataset_sha256": setup["dataset_sha256"], "catalog_content_sha256": setup["catalog_content_sha256"],
              "planned_cases": len(cases), "catalog_size": setup["catalog_size"],
              "models": sorted({model if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", model) else "[nonstandard model ID]" for model in models}),
              "configuration": configuration, "summary": summarize(records, len(cases), setup["cases_by_language"]), "records": records,
              "completed_cold_dataset": cold_complete, "warm_checks_passed": warm_checks_passed,
              "completed_full_dataset": cold_complete and warm_checks_passed and not interrupted,
              "interrupted": interrupted, "requests": metrics, "max_http_requests_including_retries": max_requests,
              "billed_cost_usd": None, "estimated_jev_cost_usd": None, "rates": rates,
              "host_task_evaluation": {"performed": False, "success_rate": None, "total_cost_usd": None, "completion_seconds": None},
              "limits": [
                  "Bundled cases are authored starter checks over six example skills, not representative workload evidence.",
                  "Cold means decision cache cleared; the HTTP connection pool and filesystem cache remain warm after the first case.",
                  "Cold and warm latency measure Router.route only, including its catalog checks, provider calls and selected-content reads; evaluator accounting is excluded, including on errors.",
                  "Accuracy includes errors among attempted cases; unattempted cases are reported separately. Early termination can bias results.",
                  "Context counts compare actual router serialization with a modeled progressive-disclosure inventory using the same selected content.",
                  "Bytes are not tokens or bills. Main-model selection, host framing, final task success and total completion time are not measured.",
                  "Usage missing from a failed or retried request is unknown, not zero cost. Explicit rates produce an estimate, never a verified invoice.",
              ]}
    # Cost is filled only when every transport attempt has complete usage and
    # the observed exact model matches the explicitly supplied rates.
    if rates and models == {rates["model"]} and metrics["usage_complete"] and report["completed_full_dataset"] and not interrupted:
        report["estimated_jev_cost_usd"] = (metrics["input_tokens"] * rates["input_usd_per_million"]
                                            + metrics["output_tokens"] * rates["output_usd_per_million"]) / 1_000_000
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", type=Path, default=ROOT / "examples/evaluation.jsonl")
    parser.add_argument("--config", type=Path, help="Router configuration; default is the bundled six example skills.")
    parser.add_argument("--allow-live", action="store_true", help="Authorize billed requests and sending tasks/catalog evidence to TypeSafe.")
    parser.add_argument("--preflight", action="store_true", help="Always prevent API calls and credential lookup, even with --allow-live.")
    parser.add_argument("--max-requests", type=int, default=64, help="Global transport-attempt cap, including retries (1–1000).")
    parser.add_argument("--rates", type=Path, help="Optional exact-model USD rates JSON; no prices are assumed.")
    parser.add_argument("--compare-report", type=Path, help="Compare compatible previous routing results on paired cases.")
    parser.add_argument("--out", type=Path, help="Report path; default goes under ignored jev-local-results/.")
    args = parser.parse_args(argv)
    if not 1 <= args.max_requests <= 1000:
        parser.error("--max-requests must be 1–1000.")
    try:
        cases = load_cases(args.dataset)
        config = Config.load(args.config) if args.config else Config(roots=[str(ROOT / "examples/skills")], retries=0)
        config = replace(config, mode="live", cache_seconds=600)
        probe = Router(config)
        try:
            setup = preflight(cases, probe, args.max_requests)
        finally:
            probe.close()
        if not args.allow_live or args.preflight:
            if args.out:
                atomic_json(args.out, setup)
            print(json.dumps(setup, indent=2))
            return 0
        rates = load_rates(args.rates)
        # Validate comparison identity/shape before any paid request.
        if args.compare_report:
            compare_report(args.compare_report, {**setup, "planned_cases": len(cases), "records": [], "configuration": {}})
        key = api_key()
        client = JevClient(config, key, max_requests=args.max_requests)
        report = evaluate(config, cases, client, max_requests=args.max_requests, rates=rates)
        report["comparison"] = compare_report(args.compare_report, report)
        destination = args.out or ROOT / "jev-local-results" / (datetime.now(timezone.utc).strftime("evaluation-%Y%m%d-%H%M%S-%f") + ".json")
        if args.out is None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            (destination.parent / ".gitignore").write_text("*\n", encoding="utf-8")
        # Raw errors, request bodies and response bodies never enter reports.
        report = redact_strings(report, key)
        atomic_json(destination, report)
        print(json.dumps({"live": True, "summary": report["summary"], "report_saved": True,
                          "completed_full_dataset": report["completed_full_dataset"]}, indent=2))
        return 0 if report["completed_full_dataset"] else 1
    except (RouterError, OSError, ValueError, TypeError):
        print("Evaluation could not complete. Check the dataset, configuration, credentials or comparison/rates input locally; sensitive details are not printed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
