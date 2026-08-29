#!/usr/bin/env python3
"""Tests for the lightweight qmd MCP HTTP client."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import qmd_mcp  # noqa: E402


class StubMcpHandler(BaseHTTPRequestHandler):
    """Minimal MCP streamable HTTP server stub."""

    # Class-level state, set per test via StubMcpServer.
    requests: list[tuple[str, dict]] = []
    session_ids: set[str] = set()
    tools_call_mode: str = "json"  # "json" | "sse" | "is_error" | "rpc_error"

    def log_message(self, *args) -> None:  # silence request logging
        pass

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        message = json.loads(self.rfile.read(length))
        StubMcpHandler.requests.append(
            (
                self.headers.get("mcp-session-id"),
                message,
            )
        )
        method = message.get("method", "")

        if method == "initialize":
            self._send(
                200,
                "application/json",
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {"name": "stub", "version": "0.0.1"},
                        "instructions": "stub instructions",
                    },
                },
                session_id="stub-session-1",
            )
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
        elif method == "tools/list":
            self._check_session()
            self._send(
                200,
                "application/json",
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "status",
                                "description": "Stub status tool.",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )
        elif method == "tools/call":
            self._check_session()
            mode = StubMcpHandler.tools_call_mode
            if mode == "sse":
                payload = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "content": [
                            {"type": "text", "text": "sse line one\nsse line two"}
                        ]
                    },
                }
                body = (
                    "event: message\n"
                    f"data: {json.dumps(payload)}\n\n"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif mode == "is_error":
                self._send(
                    200,
                    "application/json",
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": "boom: bad arg"}],
                        },
                    },
                )
            elif mode == "rpc_error":
                self._send(
                    200,
                    "application/json",
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32601, "message": "Method not found"},
                    },
                )
            else:  # json
                self._send(
                    200,
                    "application/json",
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {
                            "content": [
                                {"type": "text", "text": "status: ok"},
                                {"type": "text", "text": "docs: 3"},
                            ]
                        },
                    },
                )
        else:
            self._send(
                200,
                "application/json",
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32601, "message": f"unknown {method}"},
                },
            )

    def _check_session(self) -> None:
        if (
            StubMcpHandler.session_ids
            and self.headers.get("mcp-session-id") not in StubMcpHandler.session_ids
        ):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'missing or unknown "mcp-session-id"')
            return
        if self.headers.get("mcp-session-id"):
            StubMcpHandler.session_ids.add(
                self.headers.get("mcp-session-id")
            )

    def _send(
        self,
        code: int,
        content_type: str,
        payload: dict,
        session_id: str | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if session_id:
            self.send_header("mcp-session-id", session_id)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class StubMcpServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), StubMcpHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/mcp"

    def start(self) -> None:
        StubMcpHandler.requests = []
        StubMcpHandler.session_ids = set()
        StubMcpHandler.tools_call_mode = "json"
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class QmdMcpClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = StubMcpServer()
        self.stub.start()
        self.client = qmd_mcp.QmdMcpClient(self.stub.url)

    def tearDown(self) -> None:
        self.stub.stop()

    def test_initializes_once_and_reuses_session(self) -> None:
        self.client.tools()
        self.client.tools()
        methods = [msg.get("method") for _, msg in StubMcpHandler.requests]
        self.assertEqual(
            methods,
            ["initialize", "notifications/initialized", "tools/list", "tools/list"],
        )
        # Both tools/list requests carry the session id from initialize.
        for session_id, _ in StubMcpHandler.requests[2:]:
            self.assertEqual(session_id, "stub-session-1")

    def test_tools_lists_tools(self) -> None:
        tools = self.client.tools()
        self.assertEqual([tool["name"] for tool in tools], ["status"])

    def test_call_tool_extracts_text(self) -> None:
        result = self.client.call_tool("status")
        self.assertEqual(self.client.extract_text(result), "status: ok\ndocs: 3")
        self.assertFalse(result.get("isError"))

    def test_call_tool_sse_response(self) -> None:
        StubMcpHandler.tools_call_mode = "sse"
        result = self.client.call_tool("status")
        self.assertEqual(
            self.client.extract_text(result), "sse line one\nsse line two"
        )

    def test_extract_text_handles_resource_content(self) -> None:
        result = {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "uri": "qmd://notes/a.md",
                        "mimeType": "text/markdown",
                        "text": "# A\nbody",
                    },
                },
                {"type": "text", "text": "trailer"},
            ]
        }
        self.assertEqual(
            qmd_mcp.QmdMcpClient.extract_text(result), "# A\nbody\ntrailer"
        )

    def test_call_tool_is_error_flag_preserved(self) -> None:
        StubMcpHandler.tools_call_mode = "is_error"
        result = self.client.call_tool("status")
        self.assertTrue(result.get("isError"))
        self.assertEqual(self.client.extract_text(result), "boom: bad arg")

    def test_rpc_error_raises(self) -> None:
        StubMcpHandler.tools_call_mode = "rpc_error"
        with self.assertRaises(qmd_mcp.QmdMcpError) as ctx:
            self.client.call_tool("nope")
        self.assertIn("Method not found", str(ctx.exception))

    def test_server_instructions(self) -> None:
        self.assertEqual(self.client.server_instructions(), "stub instructions")
        self.assertEqual(self.client.server_info["name"], "stub")

    def test_unreachable_server_gives_hint(self) -> None:
        client = qmd_mcp.QmdMcpClient("http://127.0.0.1:9/mcp", timeout=1)
        with self.assertRaises(qmd_mcp.QmdMcpError) as ctx:
            client.tools()
        self.assertIn("qmd mcp --http", str(ctx.exception))


class QmdMcpCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = StubMcpServer()
        self.stub.start()
        self.argv = ["--url", self.stub.url]

    def tearDown(self) -> None:
        self.stub.stop()

    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = qmd_mcp.main(list(self.argv) + list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_tools_command_prints_names(self) -> None:
        code, out, err = self._run("tools")
        self.assertEqual(code, 0)
        self.assertIn("status", out)
        self.assertEqual(err, "")

    def test_call_command_prints_text(self) -> None:
        code, out, err = self._run("call", "status")
        self.assertEqual(code, 0)
        self.assertEqual(out, "status: ok\ndocs: 3\n")

    def test_call_command_with_json_arguments(self) -> None:
        code, out, _ = self._run("call", "status", '{"foo": 1}')
        self.assertEqual(code, 0)
        sent = [msg for _, msg in StubMcpHandler.requests if msg.get("method") == "tools/call"]
        self.assertEqual(sent[0]["params"]["arguments"], {"foo": 1})
        self.assertEqual(out, "status: ok\ndocs: 3\n")

    def test_call_is_error_returns_1(self) -> None:
        StubMcpHandler.tools_call_mode = "is_error"
        code, out, err = self._run("call", "status")
        self.assertEqual(code, 1)
        self.assertIn("boom: bad arg", err)
        self.assertEqual(out, "")

    def test_invalid_arguments_rejected(self) -> None:
        code, _, err = self._run("call", "status", "not-json")
        self.assertEqual(code, 1)
        self.assertIn("must be a JSON object", err)

    def test_non_object_arguments_rejected(self) -> None:
        code, _, err = self._run("call", "status", '[1, 2]')
        self.assertEqual(code, 1)
        self.assertIn("must be a JSON object", err)


class SseParseTest(unittest.TestCase):
    def test_picks_expected_id_and_skips_garbage(self) -> None:
        text = (
            "event: message\n"
            "data: {\"jsonrpc\": \"2.0\", \"id\": 99, \"result\": {}}\n\n"
            "data: not-json\n\n"
            "event: message\n"
            "data: {\"jsonrpc\": \"2.0\", \"id\": 7, \"result\": {\"ok\": 1}}\n\n"
        )
        payload = qmd_mcp._parse_sse_message(text, 7)
        self.assertEqual(payload["result"], {"ok": 1})

    def test_missing_id_raises(self) -> None:
        with self.assertRaises(qmd_mcp.QmdMcpError):
            qmd_mcp._parse_sse_message("data: {\"id\": 1}\n\n", 2)


if __name__ == "__main__":
    unittest.main()
