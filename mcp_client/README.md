# mcp_client

A lightweight, **stdlib-only** MCP client for the **Streamable HTTP** transport.
It talks to any MCP server exposed over HTTP — most commonly `qmd` run as
`qmd mcp --http` (default `http://127.0.0.1:8181/mcp`).

No third-party dependencies; Python 3.9+. One importable module that is also a
CLI, so it is trivial to copy next to a skill or call from a script.

## Why

qmd (and other local MCP servers) can run as an HTTP endpoint. A harness or
skill that does not have native MCP support can still use those tools through
this client: it performs the `initialize` handshake, tracks the
`Mcp-Session-Id`, and issues `tools/list` / `tools/call` requests. Responses
may arrive as plain JSON or as an SSE stream; both are handled.

## CLI

```bash
# Server info (handshake result: serverInfo, capabilities, instructions)
python3 mcp_client/mcp_client.py info

# List tools (name, params, first description line)
python3 mcp_client/mcp_client.py list-tools

# Call a tool; arguments are a JSON object (default "{}")
python3 mcp_client/mcp_client.py call status
python3 mcp_client/mcp_client.py call query \
  '{"searches":[{"type":"lex","query":"cockpit OKR Goodhart"}],"intent":"find the concept note"}'

# Non-default endpoint (also via $MCP_URL), raw JSON output
python3 mcp_client/mcp_client.py --url http://127.0.0.1:8181/mcp list-tools --json
```

For `call`, the tool's `text` content is printed by default; use `--json` for
the full result envelope. A tool result marked `isError` exits non-zero.

## Library

```python
import mcp_client

client = mcp_client.McpClient("http://127.0.0.1:8181/mcp")  # auto-connects on first call
tools = client.list_tools()
result = client.call_tool("status", {})
print(mcp_client.result_text(result))

# Or connect explicitly to inspect the server first:
info = client.connect()
print(info["serverInfo"], info.get("instructions"))
```

`McpClient(url, *, timeout=30.0, protocol_version="2025-03-26", headers=None)`.
Errors raise `mcp_client.McpError` (connection/protocol) or its subclass
`mcp_client.McpHttpError` (non-2xx HTTP status).

## Tests

```bash
python3 mcp_client/tests/test_mcp_client.py
```

Tests run against a fake in-process MCP HTTP server (`http.server`), so they do
not require qmd (or any network) to be running.

## Scope & limits

- Tool listing and tool calls only — no resources, prompts, sampling, or
  client-side elicitation.
- No long-lived `GET` SSE stream (server→client push). qmd returns tool results
  inline in the POST response, so a tool-calling client does not need it.
- One request per POST (no JSON-RPC batching).
