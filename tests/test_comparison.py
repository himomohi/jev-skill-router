"""Scoring/accounting contract tests; no model or paid API requests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jev_skill_router.config import Config, RouterError
from jev_skill_router.router import Router

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("compare_routing", ROOT / "scripts/compare_routing.py")
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def test_authored_dataset_has_language_category_coverage_and_unique_ids():
    cases = comparison.load_cases(ROOT / "examples/comparison/cases.jsonl")
    assert len(cases) == 96
    assert sum(row["language"] == "ko" for row in cases) == 48
    assert sum(row["language"] == "en" for row in cases) == 48
    assert sum(not row["expected"] for row in cases) == 12
    assert sum(len(row["expected"]) == 2 for row in cases) == 8
    assert sum(row["category"] == "near-miss" for row in cases) == 12
    assert len({row["case_id"] for row in cases}) == 96
    manifest = json.loads((ROOT / "examples/comparison/manifest.json").read_text())
    assert "Not human-validated" in manifest["holdout_status"]


def test_default_run_cannot_read_credentials_or_create_live_client(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(comparison.live, "api_key", lambda: pytest.fail("Credential read"))
    monkeypatch.setattr(comparison.live, "JevClient", lambda *a, **k: pytest.fail("HTTP client created"))
    report_path = tmp_path / "comparison.json"
    assert comparison.main(["--allow-live", "--preflight", "--out", str(report_path)]) == 0
    report = json.loads(report_path.read_text())
    assert not report["live_performed_this_run"] and not report["credentials_read"]
    assert report["http_requests_this_run"] == 0
    assert report["planned_cases"] == 96 and report["catalog_size"] == 16
    assert set(report["methods"]) == {"bm25-top1", "bm25-threshold"}
    assert all(method["summary"]["attempted"] == 96 for method in report["methods"].values())
    assert not report["host_task_evaluation"]["performed"]
    assert "task" not in report["methods"]["bm25-top1"]["records"][0]
    assert report['candidate_retrieval']['index_applied']
    assert report['candidate_retrieval']['candidate_limit'] == 8


def test_retrieval_retention_is_not_selection_accuracy(make_skill):
    for i in range(9):
        directory = make_skill(f'skill-{i}', description='Shared operation')
    router = Router(Config(roots=[str(directory.parent)]))
    cases = [{'task': 'unrelatedterm', 'context': '', 'expected': ['skill-1'], 'language': 'en'},
             {'task': 'Shared operation', 'context': '', 'expected': [], 'language': 'en'}]
    measured = comparison.retrieval_coverage(cases, router.catalog.skills.values(), 8)
    assert measured['micro_recall'] == 0 and measured['required_cases'] == 1
    assert measured['records'][1]['candidate_count'] == 8
    assert comparison.retrieval_coverage(cases, router.catalog.skills.values(), 64)['micro_recall'] == 1


def test_baseline_has_no_labels_and_deterministic_tie_breaks():
    skills = [SimpleNamespace(name="b", description="quartz tracing"), SimpleNamespace(name="a", description="quartz tracing")]
    baseline = comparison.BM25Baseline(skills)
    assert baseline.select("quartz tracing", method="bm25-top1", max_skills=3) == ["a"]
    assert baseline.select("unrelated banana", method="bm25-top1", max_skills=3) == []
    assert comparison.terms("ＤＯＣＫＥＲ 한국어") == comparison.terms("docker 한국어")


def test_set_scoring_cannot_call_partial_selection_exact():
    row = {"expected": ["one", "two"], "language": "en", "category": "multi-skill"}
    record = comparison.measure_record(0, row, ["one", "extra"], .2)
    assert not record["correct"]
    assert record["true_positives"] == record["false_positives"] == record["false_negatives"] == 1
    summary = comparison.summarize([record], 3)
    assert summary["micro_precision"] == summary["micro_recall"] == .5
    assert summary["unattempted"] == 2


def test_pairs_use_shared_case_denominator_only():
    methods = {"a": {"records": [{"case": 0, "correct": True}, {"case": 1, "correct": False}]},
               "b": {"records": [{"case": 1, "correct": True}]}}
    pair = comparison.paired_comparisons(methods)[0]
    assert pair["paired_cases"] == 1
    assert pair["left_correct"] == 0 and pair["right_correct"] == 1
    assert pair["right_minus_left_accuracy_points"] == 100


def imported_report(cases, setup):
    return {"schema_version": 3, "live": True, **setup, "planned_cases": len(cases),
            "configuration": {"model": "/private/customer", "candidate_strategy": "all"},
            "requests": {field: 0 for field in comparison.live.COUNTERS},
            "records": [{"case": 0, "status": "error", "correct": False, "seconds": 1., "expected_count": len(cases[0]["expected"]), "selected_count": 0,
                         "secret": "PRIVATE_IMPORT"}], "secret": "PRIVATE_IMPORT"}


def test_import_rejects_wrong_identity_and_sanitizes_extra_data():
    cases = [{"expected": ["one"], "category": "direct", "language": "ko"}]
    setup = {"dataset_sha256": "a", "catalog_content_sha256": "b"}
    report = imported_report(cases, setup)
    validated = comparison.validate_live_report(report, setup, cases)
    assert "PRIVATE_IMPORT" not in json.dumps(validated)
    assert "/private/customer" not in json.dumps(validated)
    assert validated["summary"]["errors"] == 1
    assert validated["summary"]["micro_recall"] is None
    report["dataset_sha256"] = "other"
    with pytest.raises(RouterError):
        comparison.validate_live_report(report, setup, cases)


@pytest.mark.parametrize("mutation", [
    {"case": True}, {"case": -1}, {"correct": True}, {"seconds": float("nan")},
    {"seconds": -1}, {"selected_count": True}, {"selected_count": 4}, {"expected_count": 0},
])
def test_imported_error_record_must_have_valid_counts_and_status(mutation):
    cases = [{"expected": ["one"], "category": "direct", "language": "ko"}]
    setup = {"dataset_sha256": "a", "catalog_content_sha256": "b"}
    report = imported_report(cases, setup)
    report["records"][0].update(mutation)
    with pytest.raises(RouterError):
        comparison.validate_live_report(report, setup, cases)


def test_invalid_import_fails_before_live_credential_access(tmp_path, monkeypatch, capsys):
    report = tmp_path / "bad.json"
    report.write_text('{}')
    monkeypatch.setattr(comparison.live, "api_key", lambda: pytest.fail("Invalid import read credential"))
    assert comparison.main(["--allow-live", "--jev-report", str(report)]) == 2


def test_shared_budget_counts_all_strategy_requests(tmp_path, monkeypatch, capsys):
    if "candidate_strategy" not in Config.__dataclass_fields__:
        pytest.skip("indexed configuration is not yet present in this checkout")
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps({"task": "Debug Python traceback", "expected": ["python-debug"]}))
    limits = []
    monkeypatch.setattr(comparison.live, "api_key", lambda: "private-credential")
    monkeypatch.setattr(comparison.live, "JevClient", lambda config, key, max_requests: limits.append(max_requests) or object())
    def evaluate(config, cases, client, max_requests, rates):
        router = Router(config)
        try:
            setup = comparison.live.preflight(cases, router, max_requests)
        finally:
            router.close()
        result = imported_report(cases, {k: setup[k] for k in ("dataset_sha256", "catalog_content_sha256")})
        complete = max_requests >= 2
        result["records"][0].update(status="selected" if complete else "error", correct=complete, selected_count=int(complete))
        result["configuration"] = {"candidate_strategy": config.candidate_strategy}
        result["requests"]["http_requests"] = min(2, max_requests)
        result["completed_full_dataset"] = complete
        return result
    monkeypatch.setattr(comparison.live, "evaluate", evaluate)
    output = tmp_path / "report.json"
    assert comparison.main([str(dataset), "--allow-live", "--strategy", "both", "--max-requests", "3", "--out", str(output)]) == 1
    assert limits == [3, 1]
    assert json.loads(output.read_text())["http_requests_this_run"] == 3


def test_host_import_uses_pairs_and_keeps_missing_cost_unknown(tmp_path):
    setup = {"dataset_sha256": "a", "catalog_content_sha256": "b"}
    data = {"schema_version": 1, **setup, "private_payload": "DO_NOT_EXPORT", "records": [
        {"case": 0, "strategy": "native", "task_success": True, "seconds": 3., "reported_cost_usd": .2},
        {"case": 0, "strategy": "routed", "task_success": True, "seconds": 2., "reported_cost_usd": None},
        {"case": 1, "strategy": "native", "task_success": False, "seconds": 8., "reported_cost_usd": .3},
    ]}
    path = tmp_path / "host.json"
    path.write_text(json.dumps(data))
    result = comparison.import_host_results(path, setup, [{}, {}])
    assert result["imported"] and not result["performed"]
    assert result["paired_cases"] == 1
    assert result["strategies"]["native"]["unpaired_records_excluded"] == 1
    assert result["strategies"]["native"]["reported_cost_usd_total"] == .2
    assert result["strategies"]["routed"]["reported_cost_usd_total"] is None
    assert "DO_NOT_EXPORT" not in json.dumps(result)
    data["records"].append(data["records"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(RouterError):
        comparison.import_host_results(path, setup, [{}, {}])


def test_host_import_cannot_treat_failure_as_string_boolean(tmp_path):
    setup = {"dataset_sha256": "a", "catalog_content_sha256": "b"}
    path = tmp_path / "host.json"
    path.write_text(json.dumps({"schema_version": 1, **setup, "records": [
        {"case": 0, "strategy": "native", "task_success": "false", "seconds": 3.}
    ]}))
    with pytest.raises(RouterError):
        comparison.import_host_results(path, setup, [{}])
