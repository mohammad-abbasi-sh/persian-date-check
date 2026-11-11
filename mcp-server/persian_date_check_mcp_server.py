#!/usr/bin/env python3
"""MCP server for persian-date-check — expose the Shamsi date auditor
as tools for any MCP client.

Zero-dependency (Python standard library only). Speaks JSON-RPC 2.0
over stdio, newline-delimited, following the MCP lifecycle:

    initialize -> notifications/initialized -> tools/list -> tools/call

Tools:
    check_persian_dates
        text    Persian text to audit (string, optional)
        files   files to audit (array of paths, optional)
        today   reference date YYYY-MM-DD for relative dates
                (default: today)
        strict  also fail on warnings (bool)
        One of text / files is required.
    convert_date
        date       date as YYYY-MM-DD (required)
        direction  "to-jalali" | "to-gregorian" (required)
    today
        (no arguments) today's date in both calendars

check_persian_dates runs skills/persian-date-check/scripts/
persian_date_check.py as a subprocess with --json and returns the
findings. Exit-code semantics are preserved in the returned text
(0 = no errors, 1 = errors found, 2 = usage error or unreadable file).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE.parent / "skills" / "persian-date-check" / "scripts" \
    / "persian_date_check.py"

SERVER_INFO = {"name": "persian-date-check", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"


def run_checker(args):
    text = args.get("text")
    files = args.get("files")
    if not text and not files:
        raise ValueError("check_persian_dates requires 'text' or 'files'")
    if isinstance(files, str):
        files = [files]
    cmd = [sys.executable, str(CHECKER), "check"]
    if files:
        cmd += [str(f) for f in files]
    if args.get("today"):
        cmd += ["--today", str(args["today"])]
    if args.get("strict"):
        cmd.append("--strict")
    cmd.append("--json")
    if text and not files:
        proc = subprocess.run(cmd, input=text, capture_output=True,
                              text=True, timeout=300)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=300)
    lines = ["check_persian_dates exit code: %d" % proc.returncode]
    try:
        summary = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        summary = {}
    if summary:
        counts = summary.get("counts", {})
        lines.append("%s error(s), %s warning(s)." % (
            counts.get("error", "?"), counts.get("warning", "?")))
        for finding in summary.get("findings", []):
            where = finding.get("file", "")
            line = " line %s" % finding["line"] if finding.get("line") else ""
            lines.append("[%s] %s %s%s: %s" % (
                finding["severity"].upper(), finding["code"], where, line,
                finding["message"]))
            if finding.get("detail"):
                lines.append("    %s" % finding["detail"])
    if proc.stderr.strip():
        lines.append("stderr:")
        lines.append(proc.stderr.strip())
    return "\n".join(lines)


def run_convert(args):
    date = args.get("date")
    direction = args.get("direction")
    if not date or direction not in ("to-jalali", "to-gregorian"):
        raise ValueError(
            "convert_date requires 'date' and direction "
            "'to-jalali' | 'to-gregorian'")
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "convert", direction, str(date)],
        capture_output=True, text=True, timeout=60)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        return "convert_date failed: %s" % (proc.stderr.strip() or out)
    return out


def run_today(_args):
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "convert", "today"],
        capture_output=True, text=True, timeout=60)
    return proc.stdout.strip()


TOOLS = [
    {
        "name": "check_persian_dates",
        "description": (
            "Audit Persian text for wrong Shamsi (Jalali) dates: "
            "impossible dates (31 Aban, 30 Esfand in a non-leap year), "
            "wrong weekdays ('Friday 21 Aban 1405' — it is Thursday), "
            "mismatched Jalali/Gregorian pairs stated together, "
            "relative dates ('tomorrow') that disagree with an absolute "
            "date in the same sentence, mixed digit scripts, "
            "Arabic-Indic digits, implausible years, and month-name "
            "misspellings. Give 'text' or 'files'. Returns the failure "
            "count and the findings with the correct values."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "Persian text to audit."},
                "files": {"type": "array", "items": {"type": "string"},
                          "description": "Files to audit."},
                "today": {"type": "string",
                          "description": "Reference date YYYY-MM-DD for "
                          "relative dates (default: today)."},
                "strict": {"type": "boolean",
                           "description": "Also fail on warnings."},
            },
        },
    },
    {
        "name": "convert_date",
        "description": (
            "Convert one date between the Gregorian and Jalali (Shamsi) "
            "calendars. Date is YYYY-MM-DD in the source calendar."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string",
                         "description": "Date as YYYY-MM-DD."},
                "direction": {"type": "string",
                              "enum": ["to-jalali", "to-gregorian"]},
            },
            "required": ["date", "direction"],
        },
    },
    {
        "name": "today",
        "description": "Today's date in both calendars (Gregorian and "
                       "Jalali), with the weekday in both languages.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

_DISPATCH = {
    "check_persian_dates": run_checker,
    "convert_date": run_convert,
    "today": run_today,
}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")
    if method == "initialize":
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        _send({"jsonrpc": "2.0", "id": msg_id,
               "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        try:
            fn = _DISPATCH[name]
        except KeyError:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32602, "message": "unknown tool: %s" % name}})
            return
        try:
            text = fn(args)
        except (ValueError, subprocess.SubprocessError) as exc:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32602, "message": str(exc)}})
            return
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "content": [{"type": "text", "text": text}]}})
    else:
        _send({"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32601, "message": "method not found: %s" % method}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
