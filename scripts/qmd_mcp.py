#!/usr/bin/env python3
"""Lightweight MCP client for the local qmd HTTP MCP server.

Speaks the MCP streamable HTTP transport (JSON-RPC 2.0 over POST /mcp)
using only the standard library. qmd exposes read-only tools (status,
query, get, multi_get) when started with:

    qmd mcp --http                # default: http://127.0.0.1:8181/mcp

CLI usage:

    python3 qmd_mcp.py tools
    python3 qmd_mcp.py call status
    python3 qmd_mcp.py call query '{"searches":[{"type":"lex","query":"reindex hooks"}],"intent":"..."}'
    python3 qmd_mcp.py call get '{"path":"#abc123"}'

The endpoint defaults to http://127.0.0.1:8181/mcp and can be overridden
with the QMD_MCP_URL environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8181/mcp"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "agent-skills-qmd-client", "version": "0.1.0"}

ACCEPT_HEADER = "application/json, text/event-stream"


class QmdMcpError(Exception):
    """Raised for transport, protocol, or tool-level failures."""


class QmdMcpClient:
    """Minimal MCP streamable HTTP client.

    One client maps to one MCP session: `initialize` is performed
    lazily on the first request and the returned session id is sent
    with every subsequent request.
    """

    def __init__(self, url: str = DEFAULT_URL, timeout: float = 120.0) -> None:
        self.url = url
        self.timeout = timeout
        self._session_id: str | None = None
        self._request_id = 0
        self._server_info: dict | None = None
        self._initialize_result: dict | None = None

    @property
    def server_info(self) -> dict | None:
        return self._server_info

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tools(self) -> list[dict]:
        """Return the server's tool list (entries of tools/list)."""
        result = self._request("tools/list", {})
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a tool and return the raw MCP result object."""
        return self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )

    @staticmethod
    def extract_text(result: dict) -> str:
        """Extract readable text from a tool result.

        Handles both `text` content items and `resource` content items
        (qmd's `get` returns full documents as embedded resources).
        """
        parts = []
        for item in result.get("content", []):
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                parts.append(item.get("text", ""))
            elif item_type == "resource":
                resource = item.get("resource") or {}
                text = resource.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts)

    def server_instructions(self) -> str | None:
        """Return the server's instructions string, if it provided one."""
        return self._ensure_initialized().get("instructions")

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> dict:
        if self._initialize_result is None:
            result = self._request("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            })
            self._initialize_result = result
            self._server_info = result.get("serverInfo", {})
            # Notification is fire-and-forget; 202 Accepted, no body.
            self._notify("notifications/initialized")
        return self._initialize_result

    def _request(self, method: str, params: dict) -> dict:
        if method != "initialize":
            self._ensure_initialized()
        self._request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        body, content_type = self._post(message)
        return self._parse_response(body, content_type, expect_id=message["id"])

    def _notify(self, method: str) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        self._post(message)

    def _post(self, message: dict) -> tuple[bytes, str]:
        data = json.dumps(message).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": ACCEPT_HEADER,
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        req = urllib.request.Request(
            self.url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("mcp-session-id")
                if sid:
                    self._session_id = sid
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise QmdMcpError(
                f"MCP HTTP error {exc.code} from {self.url}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise QmdMcpError(
                f"Cannot reach MCP server at {self.url} ({exc.reason}). "
                "Is qmd running? Start it with: qmd mcp --http"
            ) from exc

    @staticmethod
    def _parse_response(
        body: bytes, content_type: str, expect_id: int
    ) -> dict:
        text = body.decode("utf-8", "replace")
        if not text.strip():
            return {}
        if "text/event-stream" in content_type:
            payload = _parse_sse_message(text, expect_id)
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise QmdMcpError(
                    f"Invalid JSON in MCP response: {text[:200]}"
                ) from exc
        if "error" in payload:
            err = payload["error"]
            raise QmdMcpError(
                f"MCP error {err.get('code')}: {err.get('message')}"
            )
        return payload.get("result", {})


def _parse_sse_message(text: str, expect_id: int) -> dict:
    """Extract the JSON-RPC message with the expected id from an SSE body."""
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    for data in data_lines:
        if not data:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if payload.get("id") == expect_id:
            return payload
    raise QmdMcpError(
        f"No JSON-RPC response with id={expect_id} in SSE stream: {text[:200]}"
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _default_url() -> str:
    return os.environ.get("QMD_MCP_URL", DEFAULT_URL)


def _load_arguments(raw: str | None) -> dict:
    if raw is None or not raw.strip():
        return {}
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QmdMcpError(f"Tool arguments must be a JSON object: {exc}") from exc
    if not isinstance(args, dict):
        raise QmdMcpError("Tool arguments must be a JSON object")
    return args


def _print_tool(tool: dict) -> None:
    schema = tool.get("inputSchema")
    schema_text = json.dumps(schema, sort_keys=True) if schema else "{}"
    print(f"{tool['name']}  {schema_text}")
    description = (tool.get("description") or "").strip()
    if description:
        first_line = description.splitlines()[0]
        print(f"    {first_line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lightweight MCP client for the local qmd HTTP MCP server."
    )
    parser.add_argument(
        "--url",
        default=None,
        help=f"MCP endpoint URL (default: $QMD_MCP_URL or {DEFAULT_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Request timeout in seconds (default: 120)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="List available tools and their input schemas")
    sub.add_parser("instructions", help="Print server instructions, if provided")

    call = sub.add_parser("call", help="Call a tool")
    call.add_argument("tool", help="Tool name (e.g. status, query, get, multi_get)")
    call.add_argument(
        "arguments",
        nargs="?",
        default=None,
        help='JSON object of tool arguments (default: "{}")',
    )

    args = parser.parse_args(argv)
    url = args.url or _default_url()

    try:
        client = QmdMcpClient(url, timeout=args.timeout)
        if args.command == "tools":
            for tool in client.tools():
                _print_tool(tool)
        elif args.command == "instructions":
            instructions = client.server_instructions()
            print(instructions if instructions is not None else "(none)")
        elif args.command == "call":
            result = client.call_tool(args.tool, _load_arguments(args.arguments))
            if result.get("isError"):
                text = client.extract_text(result) or "tool reported an error"
                print(text, file=sys.stderr)
                return 1
            print(client.extract_text(result) or json.dumps(result, indent=2))
    except QmdMcpError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
