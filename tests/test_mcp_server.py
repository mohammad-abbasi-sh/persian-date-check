"""End-to-end tests for the persian-date-check MCP server (stdio)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SERVER = (HERE.parent / "mcp-server"
          / "persian_date_check_mcp_server.py")


def _session(calls):
    """Run the server, send a list of request dicts, return responses."""
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8")
    try:
        payload = "".join(json.dumps(c, ensure_ascii=False) + "\n"
                          for c in calls)
        out, _ = proc.communicate(payload, timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
    responses = [json.loads(line) for line in out.splitlines()
                 if line.strip()]
    return responses


def _init():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {}, "clientInfo": {"name": "test",
                                                          "version": "0"}}}


def _call(call_id, name, args):
    return {"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
            "params": {"name": name, "arguments": args}}


def test_initialize_and_list():
    resps = _session([
        _init(),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    by_id = {r["id"]: r for r in resps if "id" in r}
    assert by_id[1]["result"]["serverInfo"]["name"] == "persian-date-check"
    names = [t["name"] for t in by_id[2]["result"]["tools"]]
    assert names == ["check_persian_dates", "convert_date", "today"]


def test_call_check_text():
    resps = _session([
        _init(),
        _call(2, "check_persian_dates",
              {"text": "مهلت جمعه ۲۱ آبان ۱۴۰۵ است.",
               "today": "2026-11-11"}),
    ])
    text = resps[1]["result"]["content"][0]["text"]
    assert "exit code: 1" in text
    assert "PDC-02" in text
    assert "پنجشنبه" in text


def test_call_check_clean_text():
    resps = _session([
        _init(),
        _call(2, "check_persian_dates",
              {"text": "مهلت پنجشنبه ۲۱ آبان ۱۴۰۵ است.",
               "today": "2026-11-11"}),
    ])
    text = resps[1]["result"]["content"][0]["text"]
    assert "exit code: 0" in text
    assert "0 error(s)" in text


def test_call_check_files():
    resps = _session([
        _init(),
        _call(2, "check_persian_dates",
              {"files": [str(HERE / "fixtures" / "broken-fa.md")],
               "today": "2026-11-11"}),
    ])
    text = resps[1]["result"]["content"][0]["text"]
    assert "5 error(s)" in text


def test_call_convert():
    resps = _session([
        _init(),
        _call(2, "convert_date",
              {"date": "2026-11-11", "direction": "to-jalali"}),
        _call(3, "convert_date",
              {"date": "1405-08-20", "direction": "to-gregorian"}),
    ])
    assert "20 آبان 1405" in resps[1]["result"]["content"][0]["text"]
    assert "2026-11-11" in resps[2]["result"]["content"][0]["text"]


def test_call_today():
    resps = _session([_init(), _call(2, "today", {})])
    text = resps[1]["result"]["content"][0]["text"]
    assert "Gregorian:" in text and "Jalali:" in text


def test_call_unknown_tool_errors():
    resps = _session([_init(), _call(2, "nope", {})])
    assert resps[1]["error"]["code"] == -32602


def test_call_missing_args_errors():
    resps = _session([_init(), _call(2, "check_persian_dates", {})])
    assert resps[1]["error"]["code"] == -32602
