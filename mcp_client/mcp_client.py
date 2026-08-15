#!/usr/bin/env python3
"""A lightweight MCP client over the Streamable HTTP transport.

Stdlib only. Works against any MCP server that exposes a Streamable HTTP
endpoint — most notably ``qmd`` run as ``qmd mcp --http`` (default
``http://127.0.0.1:8181/mcp``).

Transport
---------
Streamable HTTP uses a single endpoint. The client:

1. POSTs ``initialize`` and records the ``Mcp-Session-Id`` the server returns.
2. POSTs the ``notifications/initialized`` notification (with the session id).
3. POSTs JSON-RPC requests (``tools/list``, ``tools/call``), each carrying the
   session id.

Each POST response is either a single ``application/json`` JSON-RPC message or
a ``text/event-stream`` (SSE) body carrying one or more messages; both are
handled. The response whose ``id`` matches the request is returned.

Scope (kept deliberately small):
- Tool calls and tool listing only (no resources, prompts, or sampling).
- No long-lived ``GET`` SSE stream. qmd returns tool results inline in the POST
  response, so this is sufficient for a tool-calling client.
- Single request/response (no JSON-RPC batching).

Usage as a library::

    import mcp_client
    client = mcp_client.McpClient("http://127.0.0.1:8181/mcp")
    tools = client.list_tools()
    result = client.call_tool("status", {})
    print(mcp_client.result_text(result))

Usage as a CLI::

    python3 mcp_client.py info
    python3 mcp_client.py list-tools
    python3 mcp_client.py call status
    python3 mcp_client.py call query '{"searches":[{"type":"lex","query":"ok"}],"intent":"..."}'
    python3 mcp_client.py --url http://127.0.0.1:8181/mcp call get '{"file":"mb-foo/bar.md"}' --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_URL = "http://127.0.0.1:8181/mcp"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"  # first version with Streamable HTTP
_ACCEPT = "application/json, text/event-stream"


class McpError(RuntimeError):
    """Protocol-level or connection-level error."""


class McpHttpError(McpError):
    """The server returned a non-2xx HTTP status."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def parse_sse(text: str) -> List[Any]:
    """Parse an SSE body into a list of decoded JSON payloads (one per event).

    Only ``data:`` lines are honoured; ``event:``/comment lines are ignored.
    Multiple ``data:`` lines within one event are joined with newlines, per the
    SSE spec. Non-JSON payloads are skipped.
    """
    messages: List[Any] = []
    data_lines: List[str] = []

    def flush() -> None:
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        data_lines.clear()
        try:
            messages.append(json.loads(payload))
        except json.JSONDecodeError:
            pass

    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if line == "":
            flush()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    flush()
    return messages


def result_text(result: Dict[str, Any]) -> str:
    """Return the human-readable text of a tool-call result.

    Concatenates ``text`` content parts and the embedded ``text`` of ``resource``
    parts (qmd's ``get``/``multi_get`` return resource content). Returns an empty
    string when there is no text to show.
    """
    parts: List[str] = []
    for part in result.get("content") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            parts.append(part.get("text", ""))
        elif part.get("type") == "resource":
            resource = part.get("resource")
            if isinstance(resource, dict) and resource.get("text"):
                parts.append(resource["text"])
    return "\n".join(p for p in parts if p).strip()


class McpClient:
    """A minimal MCP Streamable HTTP client.

    ``connect()`` performs the handshake. ``list_tools()`` and ``call_tool()``
    auto-connect on first use, so ``McpClient(url).call_tool(...)`` works as a
    one-liner.
    """

    def __init__(
        self,
        url: str = DEFAULT_URL,
        *,
        timeout: float = 30.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.protocol_version = protocol_version
        self.session_id: Optional[str] = None
        self._extra_headers = dict(headers or {})
        self._next_id = 0
        self._connected = False

    # --- public API -----------------------------------------------------

    def connect(
        self,
        client_name: str = "mcp-client",
        client_version: str = "0.1.0",
    ) -> Dict[str, Any]:
        """Run the initialize handshake and return the server's result.

        The result contains ``serverInfo``, ``capabilities``,
        ``protocolVersion``, and (optionally) ``instructions``.
        """
        msg = self._rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        self._notify("notifications/initialized")
        self._connected = True
        return msg["result"]

    def list_tools(self) -> List[Dict[str, Any]]:
        self._ensure_connected()
        msg = self._rpc("tools/list", {})
        return msg["result"].get("tools", [])

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        self._ensure_connected()
        params: Dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        msg = self._rpc("tools/call", params)
        return msg["result"]

    # --- internals ------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected:
            self.connect()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": _ACCEPT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        headers.update(self._extra_headers)
        return headers

    def _post(self, message: Dict[str, Any]) -> tuple:
        """POST one JSON-RPC message; return ``(status, content_type, text)``."""
        data = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, method="POST", headers=self._headers()
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                session = resp.headers.get("Mcp-Session-Id")
                status = resp.status
        except urllib.error.HTTPError as exc:
            body = exc.read()
            raise McpHttpError(
                exc.code, body.decode("utf-8", "replace")
            ) from None
        except urllib.error.URLError as exc:
            raise McpError(f"cannot connect to {self.url}: {exc.reason}") from None
        if session:
            self.session_id = session
        return status, content_type, body.decode("utf-8", "replace")

    def _decode(self, content_type: str, text: str) -> List[Any]:
        ctype = (content_type or "").lower()
        if "text/event-stream" in ctype:
            return parse_sse(text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(
                f"invalid JSON from server: {exc}; body={text[:200]!r}"
            ) from None
        return [value] if isinstance(value, dict) else list(value)

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        message: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        _status, content_type, text = self._post(message)
        if not text:
            raise McpError(f"empty response to {method!r}")
        for msg in self._decode(content_type, text):
            if not isinstance(msg, dict) or msg.get("id") != request_id:
                continue
            if "error" in msg:
                err = msg["error"]
                detail = f" {err['data']}" if err.get("data") is not None else ""
                raise McpError(
                    f"{method} failed: {err.get('code')} {err.get('message')}{detail}"
                )
            return msg
        raise McpError(f"no response with id {request_id} for {method!r}")

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._post(message)


# --- CLI ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    # Shared options are attached to both the top-level parser and every
    # subparser so they can appear before OR after the subcommand. The
    # SUPPRESS default prevents the subparser from clobbering a value already
    # set by the top-level parser when the flag is omitted there.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        help="MCP HTTP endpoint (default: $MCP_URL, else %s)" % DEFAULT_URL,
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=argparse.SUPPRESS,
        help="HTTP timeout in seconds (default: 30)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print raw JSON instead of friendly text",
    )
    parser = argparse.ArgumentParser(
        prog="mcp_client",
        description="Minimal MCP Streamable-HTTP client (qmd and other local MCP servers).",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", parents=[common], help="Show server info from the initialize handshake")
    sub.add_parser("list-tools", parents=[common], help="List the server's tools")
    call = sub.add_parser("call", parents=[common], help="Call a tool")
    call.add_argument("tool", help="Tool name (e.g. status, query, get, multi_get)")
    call.add_argument(
        "args",
        nargs="?",
        default="{}",
        help="JSON object of tool arguments (default: '{}')",
    )
    return parser


def _resolve_options(args: argparse.Namespace) -> tuple:
    url = getattr(args, "url", None) or os.environ.get("MCP_URL", DEFAULT_URL)
    timeout = getattr(args, "timeout", None)
    if timeout is None:
        timeout = 30.0
    return url, timeout, getattr(args, "json", False)


def _main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    url, timeout, as_json = _resolve_options(args)
    client = McpClient(url, timeout=timeout)
    try:
        if args.cmd == "info":
            info = client.connect()
            if as_json:
                print(json.dumps(info, indent=2))
            else:
                server = info.get("serverInfo", {})
                print("server:   %s %s" % (server.get("name"), server.get("version")))
                print("protocol: %s" % info.get("protocolVersion"))
                caps = sorted(info.get("capabilities", {}))
                print("caps:     %s" % (", ".join(caps) if caps else "(none)"))
                instructions = info.get("instructions")
                if instructions:
                    print("\ninstructions:\n" + instructions)
            return 0

        if args.cmd == "list-tools":
            tools = client.list_tools()
            if as_json:
                print(json.dumps(tools, indent=2))
            else:
                for tool in tools:
                    name = tool.get("name", "?")
                    schema = tool.get("inputSchema") or {}
                    props = list((schema.get("properties") or {}).keys())
                    desc = (tool.get("description") or "").strip().splitlines()
                    line = name + (f"({', '.join(props)})" if props else "")
                    print(line)
                    if desc:
                        print("  " + desc[0])
            return 0

        if args.cmd == "call":
            try:
                arguments = json.loads(args.args)
            except json.JSONDecodeError as exc:
                print(f"error: tool arguments are not valid JSON: {exc}", file=sys.stderr)
                return 2
            if not isinstance(arguments, dict):
                print("error: tool arguments must be a JSON object", file=sys.stderr)
                return 2
            result = client.call_tool(args.tool, arguments)
            if as_json:
                print(json.dumps(result, indent=2))
            else:
                print(result_text(result) or json.dumps(result, indent=2))
            return 1 if result.get("isError") else 0

        return 2  # unreachable
    except McpError as exc:
        print(f"mcp error: {exc}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    return _main(argv)


if __name__ == "__main__":
    sys.exit(main())
