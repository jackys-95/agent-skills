#!/usr/bin/env python3
"""Capture Codex hook payloads for local hook-shape investigations.

This is research tooling, not production adapter behavior. It records hook
stdin, argv, selected environment, and lightweight parse metadata so future
Codex hook work can validate real payloads before depending on a schema.
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys


DEFAULT_OUT_DIR = "/tmp/codex_hook_payloads"
SENSITIVE_ENV_RE = re.compile(
    r"(TOKEN|SECRET|KEY|PASSWORD|COOKIE|CREDENTIAL|AUTH|SESSION)",
    re.IGNORECASE,
)
ENV_PREFIXES = (
    "CODEX",
    "ZED",
    "TERM",
    "TMUX",
    "SHELL",
    "PWD",
    "USER",
    "LOGNAME",
)


def redact_env_value(name, value):
    if SENSITIVE_ENV_RE.search(name):
        return "<redacted>"
    return value


def selected_env():
    captured = {}
    for name, value in os.environ.items():
        if name.startswith(ENV_PREFIXES):
            captured[name] = redact_env_value(name, value)
    return dict(sorted(captured.items()))


def event_name(args, parsed_stdin):
    if args.event:
        return args.event
    if isinstance(parsed_stdin, dict):
        for key in ("hook_event_name", "event_name", "hook_event", "event", "name"):
            value = parsed_stdin.get(key)
            if isinstance(value, str) and value:
                return value
    return os.environ.get("CODEX_HOOK_EVENT") or "unknown"


def safe_slug(value):
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return slug or "unknown"


def load_stdin():
    raw = sys.stdin.read()
    if not raw:
        return raw, None, None
    try:
        return raw, json.loads(raw), None
    except json.JSONDecodeError as exc:
        return raw, None, {
            "message": exc.msg,
            "line": exc.lineno,
            "column": exc.colno,
        }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Capture one Codex hook invocation for payload discovery."
    )
    parser.add_argument(
        "--event",
        help="Optional hook event label to include in the output filename and JSON.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("CODEX_PROBE_DIR", DEFAULT_OUT_DIR),
        help=f"Directory for capture JSON files. Defaults to {DEFAULT_OUT_DIR}.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    if not os.environ.get("CODEX_HOOK_PROBE"):
        return 0

    raw_stdin, stdin_json, stdin_error = load_stdin()
    event = event_name(args, stdin_json)
    now = dt.datetime.now(dt.timezone.utc)
    out_dir = pathlib.Path(args.out_dir).expanduser()

    record = {
        "schema": "codex-hook-payload-probe-v1",
        "captured_at": now.isoformat(),
        "event": event,
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "argv": sys.argv,
        "stdin_json": stdin_json,
        "stdin_json_error": stdin_error,
        "stdin_raw": raw_stdin,
        "env": selected_env(),
    }

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{safe_slug(event)}-{os.getpid()}.json"
        out_path = out_dir / filename
        out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"[Codex hook probe] failed to write capture: {exc}", file=sys.stderr)
        return 0

    print(f"[Codex hook probe] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
