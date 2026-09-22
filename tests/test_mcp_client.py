"""Actual optional SDK interoperability, separate from mock protocol unit tests."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("check_mcp_client", Path(__file__).resolve().parents[1] / "scripts/check_mcp_client.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_official_client_real_stdio_roundtrip(monkeypatch):
    pytest.importorskip("mcp", reason="Install optional MCP verification extra to run the real SDK smoke test")
    # A credential in the calling environment must not reach the offline child.
    monkeypatch.setenv("TYPESAFE_API_KEY", "DO_NOT_READ_OR_EXPORT_THIS_TEST_CREDENTIAL")
    report = asyncio.run(asyncio.wait_for(smoke.run_check(), timeout=40))
    assert report["success"] and report["api_requests"] == 0
    assert report["pages_read"] > 1
    assert not report["credentials_read"] and not report["desktop_host_tested"]
    assert "all_pages_reconstruct_utf8_source" in report["checks"]
    assert "path_traversal_rejected" in report["checks"]
    assert "DO_NOT_READ_OR_EXPORT_THIS_TEST_CREDENTIAL" not in json.dumps(report)
