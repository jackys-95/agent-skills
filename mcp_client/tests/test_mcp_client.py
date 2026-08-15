#!/usr/bin/env python3
"""Unit tests for mcp_client using a fake in-process MCP Streamable-HTTP server.

Run: python3 test_mcp_client.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_client


SESSION = "fake-session-123"

TOOLS = [
    {
        "name": "status",
        "description": "Index status.\nMore detail.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query",
        "description": "Search the knowledge base.\nMore detail.",
        "inputSchema": {
            "type": "object",
            "properties": {"searches": {"type": "array"}, "intent": {"type": "string"}},
            "required": ["searches"],
        },
    },
]


class FakeMcpHandler(BaseHTTPRequestHandler):
    """Emulates an MCP Streamable-HTTP endpoint just enough to exercise the client."""

    def log_message(self, *args) -> None:  # silence request logging
        pass

    def _json(self, obj, status=200, session: bool = True) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", SESSION)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        method = request.get("method")
        request_id = request.get("id")
        state = self.server.state
        state["requests"].append(
            {"method": method, "id": request_id, "session": self.headers.get("Mcp-Session-Id")}
        )

        if method == "initialize":
            state["session"] = SESSION
            self._json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "fake", "version": "9.9.9"},
                        "instructions": "fake instructions",
                    },
                }
            )
            return

        if method == "notifications/initialized":
            state["initialized_session"] = self.headers.get("Mcp-Session-Id")
            self.send_response(202)
            self.end_headers()
            return

        if method == "tools/list":
            self._json({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
            return

        if method == "tools/call":
            name = request["params"]["name"]
            if name == "boom":
                self._json(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "boom"},
                    }
                )
                return
            if name == "sse":
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"content": [{"type": "text", "text": "hello-sse"}]},
                    }
                )
                body = f"event: message\ndata: {payload}\n\n".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Mcp-Session-Id", SESSION)
                self.end_headers()
                self.wfile.write(body)
                return
            args = request["params"].get("arguments", {})
            self._json(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"echo:{name}:{json.dumps(args, sort_keys=True)}"}
                        ]
                    },
                }
            )
            return

        self._json(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"unknown {method}"}},
            session=False,
        )


class McpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
        cls.server.state = {"session": None, "requests": [], "initialized_session": None}
        cls.url = "http://127.0.0.1:%d/mcp" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.server.state["requests"].clear()
        self.server.state["session"] = None
        self.server.state["initialized_session"] = None

    def _requests(self, method: str):
        return [r for r in self.server.state["requests"] if r["method"] == method]

    def test_connect_captures_session_and_sends_initialized(self):
        client = mcp_client.McpClient(self.url)
        info = client.connect()
        self.assertEqual(info["serverInfo"], {"name": "fake", "version": "9.9.9"})
        self.assertEqual(info["instructions"], "fake instructions")
        self.assertEqual(client.session_id, SESSION)
        # initialized notification carried the session id
        self.assertEqual(self.server.state["initialized_session"], SESSION)
        # initialize itself must NOT carry a (not-yet-known) session id
        self.assertIsNone(self._requests("initialize")[0]["session"])

    def test_list_tools_auto_connects_and_sends_session(self):
        client = mcp_client.McpClient(self.url)
        tools = client.list_tools()
        self.assertEqual([t["name"] for t in tools], ["status", "query"])
        self.assertEqual(self._requests("tools/list")[0]["session"], SESSION)

    def test_call_tool_json_roundtrip(self):
        client = mcp_client.McpClient(self.url)
        result = client.call_tool("status", {"a": 1})
        self.assertEqual(mcp_client.result_text(result), "echo:status:{\"a\": 1}")

    def test_call_tool_sse_roundtrip(self):
        client = mcp_client.McpClient(self.url)
        result = client.call_tool("sse", {})
        self.assertEqual(mcp_client.result_text(result), "hello-sse")

    def test_call_tool_jsonrpc_error_raises(self):
        client = mcp_client.McpClient(self.url)
        with self.assertRaises(mcp_client.McpError) as ctx:
            client.call_tool("boom", {})
        self.assertIn("boom", str(ctx.exception))

    def test_connection_error_raises_mcp_error(self):
        client = mcp_client.McpClient("http://127.0.0.1:1/mcp", timeout=2)
        with self.assertRaises(mcp_client.McpError):
            client.connect()

    def test_auto_connect_is_idempotent(self):
        client = mcp_client.McpClient(self.url)
        client.call_tool("status", {})
        client.call_tool("query", {"searches": []})
        # exactly one initialize even across multiple auto-connecting calls
        self.assertEqual(len(self._requests("initialize")), 1)
        self.assertEqual(len(self._requests("tools/call")), 2)


class ParseSseTests(unittest.TestCase):
    def test_single_event(self):
        self.assertEqual(mcp_client.parse_sse('data: {"a": 1}\n\n'), [{"a": 1}])

    def test_multiple_events_and_comments(self):
        body = 'event: message\ndata: {"a": 1}\n\n: comment\nevent: message\ndata: {"b": 2}\n\n'
        self.assertEqual(mcp_client.parse_sse(body), [{"a": 1}, {"b": 2}])

    def test_multiline_data_joined(self):
        body = 'data: {"a":\ndata:  1}\n\n'
        self.assertEqual(mcp_client.parse_sse(body), [{"a": 1}])

    def test_trailing_event_without_blank_line(self):
        self.assertEqual(mcp_client.parse_sse('data: {"a": 1}'), [{"a": 1}])

    def test_skips_non_json_data(self):
        self.assertEqual(mcp_client.parse_sse("data: not-json\n\n"), [])


class CliParserTests(unittest.TestCase):
    """Lock in CLI behaviour: shared flags work before OR after the subcommand."""

    def _resolve(self, argv):
        args = mcp_client._build_parser().parse_args(argv)
        return mcp_client._resolve_options(args)

    def test_flags_after_subcommand(self):
        url, _timeout, as_json = self._resolve(["call", "status", "--json", "--url", "http://x/mcp"])
        self.assertTrue(as_json)
        self.assertEqual(url, "http://x/mcp")

    def test_flags_before_subcommand(self):
        url, _timeout, as_json = self._resolve(["--json", "--url", "http://y/mcp", "call", "status"])
        self.assertTrue(as_json)
        self.assertEqual(url, "http://y/mcp")

    def test_timeout_is_parsed(self):
        _url, timeout, _as_json = self._resolve(["--timeout", "5", "info"])
        self.assertEqual(timeout, 5.0)

    def test_defaults_when_omitted(self):
        url, timeout, as_json = self._resolve(["list-tools"])
        self.assertEqual(timeout, 30.0)
        self.assertFalse(as_json)
        self.assertEqual(url, os.environ.get("MCP_URL", mcp_client.DEFAULT_URL))

    def test_missing_subcommand_is_rejected(self):
        with self.assertRaises(SystemExit):
            mcp_client._build_parser().parse_args([])


class ResultTextTests(unittest.TestCase):
    def test_joins_text_parts(self):
        result = {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
                {"type": "image", "data": "ignored"},
            ]
        }
        self.assertEqual(mcp_client.result_text(result), "hello\nworld")

    def test_no_text_returns_empty(self):
        self.assertEqual(mcp_client.result_text({"content": []}), "")

    def test_resource_text_is_extracted(self):
        result = {
            "content": [
                {"type": "resource", "resource": {"uri": "qmd://x", "text": "doc body"}},
                {"type": "text", "text": "trailer"},
            ]
        }
        self.assertEqual(mcp_client.result_text(result), "doc body\ntrailer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
