"""Evaluation accounting tests use deterministic HTTP fixtures, never paid API calls."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from jev_skill_router.config import Config, RouterError
from jev_skill_router.jev import JevClient

SPEC = importlib.util.spec_from_file_location("evaluate_live", Path(__file__).resolve().parents[1] / "scripts/evaluate_live.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def cases():
    return [
        {"task": "PRIVATE_TASK inspect Python", "context": "/private/customer/export", "expected": ["python-debug"], "language": "en"},
        {"task": "PRIVATE_TASK inspect Python", "context": "/private/customer/export", "expected": ["python-debug"], "language": "ko"},
    ]


def measured_client(config, handler, limit=64):
    return JevClient(config, "fixture-credential-never-print", httpx.MockTransport(handler), sleep=lambda _: None, max_requests=limit)


def test_preflight_never_reads_key_or_constructs_client(monkeypatch, capsys):
    monkeypatch.setattr(evaluation, "api_key", lambda: pytest.fail("Preflight read a credential"))
    monkeypatch.setattr(evaluation, "JevClient", lambda *args, **kwargs: pytest.fail("Preflight initialized HTTP"))
    assert evaluation.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["api_requests"] == 0 and not report["credentials_read"]
    assert report["catalog_size"] == 6 and report["cases"] == 24
    assert report["cases_by_language"] == {"en": 12, "ko": 12, "other": 0}
    assert report["expected_no_match_cases"] == 6
    assert evaluation.main(["--allow-live", "--preflight"]) == 0


@pytest.mark.parametrize("row", [
    {"task": "okay", "context": [], "expected": []},
    {"task": "okay", "expected": ["python-debug", "python-debug"]},
    {"task": "가" * 3000, "expected": []},
    {"task": "okay", "expected": [], "language": "/private/path"},
])
def test_invalid_dataset_fails_before_credentials(tmp_path, row):
    path = tmp_path / "private-name.jsonl"
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(RouterError) as error:
        evaluation.load_cases(path)
    assert str(path) not in str(error.value)


def test_both_cache_paths_measured_without_exposing_payload(make_skill, provider):
    skill_root = make_skill(body="PRIVATE_BODY never include this in reports").parent
    config = Config(roots=[str(skill_root)], retries=0)
    report = evaluation.evaluate(config, cases(), measured_client(config, provider), max_requests=64)
    assert report["completed_full_dataset"]
    assert report["summary"]["exact_match_accuracy_including_errors"] == 1
    assert report["requests"]["http_requests"] == 4  # A duplicate dataset task is cold again.
    assert report["requests"]["input_tokens"] == 400
    assert report["requests"]["usage_complete"]
    assert all(not row["cache_hit"] and row["warm"]["cache_hit"] for row in report["records"])
    assert all(row["warm"]["http_requests"] == 0 and row["warm"]["same_selection"] for row in report["records"])
    assert report["summary"]["warm_cache"]["samples"] == 2
    assert report["estimated_jev_cost_usd"] is None and report["billed_cost_usd"] is None
    assert not report["host_task_evaluation"]["performed"]
    serialized = json.dumps(report)
    for private in ("PRIVATE_TASK", "PRIVATE_BODY", "fixture-credential-never-print", "/private/customer", str(skill_root), "python-debug"):
        assert private not in serialized


def test_retry_attempts_and_missing_usage_prevent_cost_claim(skill_root, provider):
    attempts = []
    def handle(request):
        attempts.append(1)
        return httpx.Response(503, json={"private": "PRIVATE_ERROR"}) if len(attempts) == 1 else provider(request)
    config = Config(roots=[str(skill_root)], retries=1)
    rates = {"model": "fixture-not-live", "input_usd_per_million": 2, "output_usd_per_million": 4}
    report = evaluation.evaluate(config, cases()[:1], measured_client(config, handle), max_requests=64, rates=rates)
    assert report["requests"]["http_requests"] == 3 and report["requests"]["api_calls"] == 2
    assert report["requests"]["retry_requests"] == 1 and report["requests"]["unreported_requests"] == 1
    assert not report["requests"]["usage_complete"] and report["estimated_jev_cost_usd"] is None
    assert "PRIVATE_ERROR" not in json.dumps(report)


def test_global_cap_includes_retries_and_retains_failure_denominators(skill_root, provider):
    attempts = []
    def handle(request):
        attempts.append(1)
        return httpx.Response(503) if len(attempts) == 1 else provider(request)
    config = Config(roots=[str(skill_root)], retries=1)
    report = evaluation.evaluate(config, cases(), measured_client(config, handle, limit=2), max_requests=2)
    assert len(attempts) == report["requests"]["http_requests"] == 2
    assert report["summary"]["attempted"] == 1 and report["summary"]["errors"] == 1
    assert report["summary"]["unattempted"] == 1
    assert report["summary"]["exact_match_accuracy_including_errors"] == 0
    assert report["summary"]["exact_match_accuracy_completed_only"] is None
    assert not report["completed_full_dataset"]


@pytest.mark.parametrize("model,expected", [("fixture-not-live", .00048), ("unrelated-model", None)])
def test_cost_estimate_requires_explicit_matching_model(skill_root, provider, model, expected):
    config = Config(roots=[str(skill_root)], retries=0)
    rates = {"model": model, "input_usd_per_million": 2, "output_usd_per_million": 4}
    report = evaluation.evaluate(config, cases()[:1], measured_client(config, provider), max_requests=64, rates=rates)
    assert report["estimated_jev_cost_usd"] == expected
    assert report["billed_cost_usd"] is None


def test_unexpected_model_text_is_not_exported_or_ignored_for_cost(skill_root, provider):
    attempts = []
    def handle(request):
        attempts.append(1)
        data = provider(request).json()
        if len(attempts) == 2:
            data["model"] = "/private/provider/model"
        return httpx.Response(200, json=data)
    config = Config(roots=[str(skill_root)], retries=0)
    rates = {"model": "fixture-not-live", "input_usd_per_million": 2, "output_usd_per_million": 4}
    report = evaluation.evaluate(config, cases()[:1], measured_client(config, handle), max_requests=64, rates=rates)
    assert report["estimated_jev_cost_usd"] is None
    assert "/private/provider/model" not in json.dumps(report)


def test_redaction_preserves_json_types():
    result = evaluation.redact_strings({"okay": False, "count": 1, "label": "contains a"}, "a")
    assert result == {"okay": False, "count": 1, "label": "cont[REDACTED]ins [REDACTED]"}


def test_interrupted_paid_case_is_retained_in_denominators(skill_root, provider, monkeypatch):
    real_route = evaluation.Router.route
    def interrupt_after_provider(self, task, context=""):
        real_route(self, task, context)
        raise KeyboardInterrupt()
    monkeypatch.setattr(evaluation.Router, "route", interrupt_after_provider)
    config = Config(roots=[str(skill_root)], retries=0)
    report = evaluation.evaluate(config, cases(), measured_client(config, provider), max_requests=64)
    assert report["interrupted"] and not report["completed_full_dataset"]
    assert report["summary"]["attempted"] == 1 and report["summary"]["errors"] == 1
    assert report["summary"]["unattempted"] == 1
    assert report["records"][0]["error_category"] == "interrupted"
    assert report["records"][0]["http_requests"] == report["requests"]["http_requests"] == 2


@pytest.mark.parametrize("failure", [RouterError("warm verification failed"), KeyboardInterrupt()])
def test_final_warm_failure_is_saved_and_cli_exits_unsuccessfully(tmp_path, skill_root, provider, monkeypatch, failure):
    real_route = evaluation.Router.route
    calls = []
    def fail_warm(self, task, context=""):
        calls.append(1)
        if len(calls) == 2:
            raise failure
        return real_route(self, task, context)
    monkeypatch.setattr(evaluation.Router, "route", fail_warm)
    monkeypatch.setattr(evaluation, "api_key", lambda: "fixture-credential-never-print")
    monkeypatch.setattr(evaluation, "JevClient", lambda config, key, **kwargs: measured_client(config, provider))
    config = Config(roots=[str(skill_root)], retries=0)
    config_path = tmp_path / "config.json"
    config.save(config_path)
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps(cases()[0]), encoding="utf-8")
    output = tmp_path / "report.json"
    assert evaluation.main([str(dataset), "--config", str(config_path), "--allow-live", "--out", str(output)]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["completed_cold_dataset"] and not report["warm_checks_passed"]
    assert not report["completed_full_dataset"]
    assert report["records"][0]["warm"]["error"]
    assert report["requests"]["http_requests"] == 2
    assert report["interrupted"] == isinstance(failure, KeyboardInterrupt)


def test_no_match_abstention_and_errors_have_explicit_denominators():
    rows = [
        {"status": "no_match", "correct": True, "expected_count": 0, "selected_count": 0, "seconds": .1, "language": "en"},
        {"status": "error", "correct": False, "expected_count": 1, "selected_count": 0, "seconds": 1., "language": "ko"},
        {"status": "selected", "correct": False, "expected_count": 0, "selected_count": 1, "seconds": .2, "language": "en"},
        {"status": "uncertain", "correct": False, "expected_count": 1, "selected_count": 0, "seconds": .3, "language": "ko"},
    ]
    summary = evaluation.summarize(rows, planned=6)
    assert summary["exact_match_accuracy_including_errors"] == .25
    assert summary["exact_match_accuracy_completed_only"] == 1 / 3
    assert summary["no_match_cases_attempted"] == 2 and summary["no_match_false_selections"] == 1
    assert summary["required_skill_cases_attempted"] == 2 and summary["required_skill_abstentions"] == 1
    assert summary["by_language"]["ko"]["errors"] == 1 and summary["unattempted"] == 2


def test_compare_rejects_changed_dataset_before_any_paid_call(tmp_path, monkeypatch):
    path = tmp_path / "previous.json"
    path.write_text(json.dumps({"schema_version": 2, "live": True, "dataset_sha256": "wrong"}), encoding="utf-8")
    monkeypatch.setattr(evaluation, "api_key", lambda: pytest.fail("Comparison failed after reading credential"))
    assert evaluation.main(["--allow-live", "--compare-report", str(path)]) == 2


def test_paired_report_comparison_ignores_unpaired_cases_and_payload(tmp_path, skill_root, provider):
    config = Config(roots=[str(skill_root)], retries=0)
    report = evaluation.evaluate(config, cases(), measured_client(config, provider), max_requests=64)
    old = json.loads(json.dumps(report))
    old["records"] = old["records"][:1]
    old["records"][0]["correct"] = False
    old["configuration"]["max_concurrency"] = 1
    old["private_extra"] = "PRIVATE_COMPARISON_TASK"
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    comparison = evaluation.compare_report(path, report)
    assert comparison["paired_cases"] == 1
    assert comparison["accuracy_change_percentage_points"] == 100
    assert not comparison["configuration_equal"]
    assert comparison["configuration_changes"]["max_concurrency"] == {"previous": 1, "current": 3}
    assert "PRIVATE_COMPARISON_TASK" not in json.dumps(comparison)
    old["records"].append(old["records"][0])
    path.write_text(json.dumps(old), encoding="utf-8")
    with pytest.raises(RouterError):
        evaluation.compare_report(path, report)
