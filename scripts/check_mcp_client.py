"""Exercise the real stdio server with the official MCP Python client SDK.

An isolated temporary offline profile is used; no API credentials or paid calls.
This proves SDK interoperability, not a Codex/Claude desktop session or Jev quality.
Install optional verification dependency: python -m pip install 'mcp>=1.12,<2'
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_skill_router.config import Config, atomic_json


async def run_check() -> dict:
    # Import here: production and default unit tests need no MCP SDK dependency.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    checks = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="jev-mcp-sdk-") as directory:
        temporary = Path(directory).resolve()
        skill = temporary / "skills" / "python-debug"
        skill.mkdir(parents=True)
        text = ("---\nname: python-debug\ndescription: Debug Python traceback failures and regression tests.\n---\n\n"
                + "Inspect traceback, reproduce the failure, then verify the fix. 한국어 전송 확인.\n" * 45)
        # Write explicit CRLF bytes on every OS; text-mode writes would translate
        # LF on Windows while the expected in-memory string still contained LF.
        text = text.replace("\n", "\r\n")
        (skill / "SKILL.md").write_bytes(text.encode("utf-8"))
        config_path = temporary / "profile" / "config.json"
        Config(roots=[str(skill.parent)], mode="offline", max_output_chars=1000).save(config_path)
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "jev_skill_router", "--config", str(config_path), "serve"],
            env={"PYTHONPATH": str(ROOT / "src"), "JEV_SKILLS_HOME": str(temporary / "profile"),
                 "TYPESAFE_API_KEY": ""},
        )

        def require(condition, check):
            if not condition:
                raise RuntimeError("MCP SDK check failed: " + check)
            checks.append(check)

        def payload(result):
            require(not result.isError, "tool_result_success")
            if len(result.content) != 1 or result.content[0].type != "text":
                raise RuntimeError("Unexpected MCP content shape")
            return json.loads(result.content[0].text)

        # Redirect stderr to a private temporary file, never expose arbitrary
        # provider/task output. A real fileno is needed by subprocess transports.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
            async with stdio_client(parameters, errlog=errlog) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                    initialized = await session.initialize()
                    require(initialized.serverInfo.name == "jev-skill-router", "initialize")
                    require(bool(initialized.instructions), "server_instructions")
                    listed = await session.list_tools()
                    require([tool.name for tool in listed.tools] == ["skill_router"], "tools_list")
                    routed = payload(await session.call_tool("skill_router", {
                        "action": "route", "task": "Debug Python traceback failures and regression tests."}))
                    require(routed["provider"] == "offline-lexical-demo" and routed["api_calls"] == 0, "offline_route_no_api")
                    require(len(routed["selected"]) == 1 and routed["selected"][0]["name"] == "python-debug", "selected_skill")
                    selected = routed["selected"][0]
                    pages = [selected["content"]]
                    offset = selected["next_offset"]
                    require(offset is not None, "pagination_exercised")
                    while offset is not None:
                        page = payload(await session.call_tool("skill_router", {
                            "action": "read", "skill_id": selected["skill_id"], "offset": offset,
                            "expected_digest": selected["content_digest"]}))
                        require(page["offset"] == offset, "continuation_offset")
                        pages.append(page["content"])
                        offset = page["next_offset"]
                    require("".join(pages) == text, "all_pages_reconstruct_utf8_source")
                    rejected = await session.call_tool("skill_router", {
                        "action": "read", "skill_id": selected["skill_id"], "path": "../../outside.txt"})
                    require(bool(rejected.isError), "path_traversal_rejected")
                    rejected = await session.call_tool("skill_router", {
                        "action": "read", "skill_id": selected["skill_id"], "offset": 1000})
                    require(bool(rejected.isError), "continuation_without_digest_rejected")
                    await session.send_ping()
                    checks.append("ping_after_errors")
                    again = payload(await session.call_tool("skill_router", {
                        "action": "route", "task": "Debug Python traceback failures and regression tests."}))
                    require(again["cache_hit"] and again["api_calls"] == 0, "warm_cache_after_errors")
    return {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
            "success": True, "client": "official-modelcontextprotocol-python-sdk", "sdk_version": version("mcp"),
            "transport": "stdio-subprocess", "protocol_version": initialized.protocolVersion,
            "server_version": initialized.serverInfo.version, "python_version": sys.version.split()[0],
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "checks": list(dict.fromkeys(checks)), "pages_read": len(pages), "source_line_endings": "CRLF",
            "api_requests": 0, "credentials_read": False, "isolated_temporary_profile": True,
            "desktop_host_tested": False, "live_jev_tested": False,
            "limitations": ["Official SDK client interoperability only; no Codex, Claude Code or Cursor desktop flow was executed.",
                            "Offline fixture selection exercises real stdio and file reads, not live Jev inference."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(asyncio.wait_for(run_check(), timeout=40))
    except ImportError:
        print("Official MCP SDK unavailable. Install the verification extra or: python -m pip install 'mcp>=1.12,<2'. No test was performed.", file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt):
        print("Official MCP SDK smoke check failed. No success claim was recorded; inspect locally without exposing sensitive output.", file=sys.stderr)
        return 1
    if args.out:
        atomic_json(args.out, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
