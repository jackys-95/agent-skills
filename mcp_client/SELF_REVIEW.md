# Self-Review — `mcp_client`

**Scope.** A critical review of (a) the `mcp_client` code and (b) the reasoning
trace used to build it. Written **after** the implementation; **no code was
changed** as a result of this review. Every finding below is tagged with the
evidence that supports it, and "recommended follow-ups" are listed but **not
applied**.

**Method.** Re-read the final source and tests fresh, then ran read-only probes
against the live qmd server (`http://localhost:8181/mcp`) and the test suite to
turn speculation into confirmed facts:

```text
python3 -m py_compile mcp_client/mcp_client.py mcp_client/tests/test_mcp_client.py   # OK
python3 mcp_client/tests/test_mcp_client.py                                          # 20 passed, ~0.62s
edge probes: malformed URLs, double connect(), 3x fresh + cold suite runs           # see §1.1
```

---

## Verdict (TL;DR)

The client is **correct for its stated scope** (a tool-calling client against a
local Streamable HTTP server) and was verified end-to-end against the live qmd
server. The unit tests are meaningful (they drive a real in-process HTTP server,
not mocks). However, the review surfaced **two real robustness defects**
(§1.1), several **documented-but-real gaps** that matter if the client is used
as a long-lived library rather than a one-shot CLI (§1.2), and — most
interestingly — a **cross-cutting bug that is not in this client at all**: the
installed qmd skill's MCP reference doc lists stale `get` parameters that
contradict the running qmd 2.5.3 (§3).

Severity key: 🔴 real defect · 🟡 gap/limitation · 🟢 minor/cosmetic.

---

## 1. Code review

### 1.1 Confirmed defects

🔴 **D1 — A schemeless `--url` escapes as an uncaught `ValueError` (raw CLI traceback).**
`_post()` (mcp_client.py:201) catches `urllib.error.HTTPError` (line 213) and
`urllib.error.URLError` (line 218) but **not `ValueError`**. `urllib` raises a
bare `ValueError` (not wrapped in `URLError`) for a URL with no scheme.
Evidence:

```text
McpClient("not a valid url")     -> UNCAUGHT ValueError: unknown url type: 'not a valid url'
McpClient("bogus://host/mcp")    -> McpError: ... unknown url type: bogus      (caught)
McpClient("http://")             -> McpError: ... no host given                (caught)

$ python3 mcp_client/mcp_client.py --url "not a valid url" call status
Traceback (most recent call last):
  ...
  File ".../mcp_client.py", line 380, in <module>   # raw traceback, not "mcp error: ..."
```

It still exits 1, but the user sees a stack trace instead of the clean
`mcp error: ...` message the CLI promises. (Bad *hostname* is fine — that path
is wrapped in `URLError`.)

🔴 **D2 — No reconnection; a stale session cannot recover, and a second `connect()` fails.**
The client caches `self.session_id` and `self._connected` and never re-runs the
handshake after a failure. If the server restarts (e.g. `qmd mcp stop` / relaunch)
or the session is invalidated, every subsequent call fails with a stale session
and the only remedy is to construct a new `McpClient`. For a **CLI** (one process
per call) this is invisible; for **library** use it is a real operational trap.
Additionally, calling `connect()` twice on one client hard-fails. Evidence
against live qmd:

```text
1st connect ok, session 5d7e88b9-...
2nd connect FAILED: HTTP 400: {"jsonrpc":"2.0","error":{"code":-32600,
    "message":"Invalid Request: Server already initialized"},"id":null}
```

Note `_ensure_connected()` (mcp_client.py:187) does prevent *automatic*
double-init across `list_tools()`/`call_tool()`, so the auto path is safe; the
exposed failure modes are (a) explicit double `connect()` and (b) server restart.

🔴 **D3 — The `McpHttpError` (non-2xx HTTP) branch is untested.**
The fake server (`test_mcp_client.py:46` `_json`) only ever returns 200/202, so
the `except urllib.error.HTTPError` handler (mcp_client.py:213) is never
exercised. `test_connection_error_raises_mcp_error` covers the *connection*
failure (`URLError`), not an HTTP error status. A regression in that branch
(status code, body decode, truncation) would not be caught.

🟡 **D4 — `$MCP_URL` is honored only by the CLI, not by the library default.**
`_resolve_options()` (mcp_client.py:309) reads `MCP_URL`, but
`McpClient.__init__` defaults `url` to the constant `DEFAULT_URL` (mcp_client.py:34)
and never consults the env var. The package README states the default as
"``$MCP_URL, else http://127.0.0.1:8181/mcp``" as if it were general. A library
caller doing `McpClient()` does **not** get the env override — a small but real
doc/behavior mismatch.

### 1.2 Design gaps / limitations (some documented, some not)

These are defensible given the "lightweight" brief, but a future maintainer
should know they are real boundaries:

- 🟡 **No long-lived `GET` SSE stream** (server→client push / progress /
  `listChanged` notifications). Documented in the module docstring. Fine for
  qmd (results are inline in the POST response); a gap for servers that rely on
  the open stream.
- 🟡 **No JSON-RPC batching** — one request per POST. Documented.
- 🟡 **No streaming of large responses** — `_post()` does `resp.read()` of the
  *entire* body into memory (mcp_client.py:211). A large `multi_get` is fully
  buffered. Acceptable at this scale, but not "lightweight" for big payloads.
- 🟡 **Not thread-safe.** `_next_id`, `session_id`, `_connected` are mutated
  without a lock (mcp_client.py:129–131). Safe for sequential/CLI use; unsafe if
  one client is shared across threads.
- 🟡 **CLI cannot pass custom headers** (e.g. `Authorization`). The library
  accepts `headers=` (mcp_client.py:120), but there is no `--header/-H` flag, so
  an authenticated MCP server is reachable only via the library, not the CLI.
- 🟡 **Loose JSON decoding edge.** `_decode()` (mcp_client.py:224) does
  `list(value)` for a non-dict; if a server ever returned a bare JSON *string*,
  that would split into characters (harmlessly skipped by `_rpc`, which requires
  `isinstance(msg, dict)`). A non-object response therefore surfaces as
  "no response with id …" rather than a clearer "malformed response" error.
  Not a crash, but the diagnostic is misleading.

### 1.3 Minor / cosmetic

- 🟢 **`resp.status` is read but never used** (mcp_client.py:212); both callers
  discard it (`_status, ...` in `_rpc`, ignored in `_notify`). urllib already
  raises on non-2xx, so no status is needed — the read is dead weight. Related
  portability nit: `addinfourl.status` is present in the tested 3.14, but
  `.getcode()` is the more universally portable accessor; the README's
  "Python 3.9+" claim is not separately verified for `.status`.
- 🟢 **Error `data` rendered as Python repr.** In `_rpc()`
  (mcp_client.py:249) `f" {err['data']}"` stringifies a dict via `repr`
  (single quotes), not JSON. Cosmetic.
- 🟢 **`parse_sse()` over-strips** each `data:` line with `.strip()`
  (mcp_client.py:80) instead of removing the single leading space per the SSE
  spec. Harmless because payloads are JSON (whitespace-insignificant), but not
  spec-faithful.
- 🟢 **Line length.** No linter config exists in the repo (verified: no
  `ruff.toml`/`pyproject.toml`/`.flake8`/etc.). Longest client line is exactly
  100 (mcp_client.py:41, a docstring example); the test file has a 108-char line
  (test_mcp_client.py:134). Not enforced, but slightly wider than the surrounding
  code's ~88–90 style.
- 🟢 **Naming.** `mcp_client/mcp_client.py` is mildly redundant. Chosen so the
  module imports as `mcp_client` and matches the repo's plain-module convention
  (`adapters/core/manifest.py`), but a package would arguably be cleaner.
- 🟢 **Type hints.** `_post`/`_resolve_options` annotate return as bare `tuple`
  rather than `Tuple[int, str, str]` / `Tuple[str, float, bool]`.

### 1.4 What is solid

- **Correct Streamable HTTP handshake**, verified live: `initialize` (carries no
  session) → capture `Mcp-Session-Id` → `notifications/initialized` (carries the
  id) → `tools/*` (carry the id). Confirmed by both the unit tests
  (`test_connect_captures_session_and_sends_initialized`) and live runs.
- **Both response encodings handled** (plain JSON *and* SSE), each with a test.
- **Clean error model** (`McpError` / `McpHttpError`) and **sensible CLI exit
  codes** (0 ok / 1 server-or-protocol error / 2 usage), all verified.
- **CLI flag positioning works before *and* after the subcommand** (the
  `argparse.SUPPRESS` shared-parent trick), with dedicated tests.
- **`result_text()`** correctly extracts both `text` and qmd's `resource`
  content, so `get`/`multi_get` print clean document text (verified live).
- **Stdlib-only, single portable file**, auto-connect one-liners, and accurate
  docs — a genuinely light dependency.

---

## 2. Thinking-trace review (process audit)

An honest accounting of how the code was produced, including where the reasoning
was weak.

1. **The one-time 35 s test run — observed, waved away, never root-caused.**
   The first `unittest` run reported `Ran 14 tests in 35.551s`. I attributed it
   to "a one-off TCP stall" on the port-1 connection test, re-ran it (0.5 s),
   and moved on. On re-examination for this review, port-1 connect is **13 ms**,
   a cold (no-`__pycache__`) full run is **0.64 s**, and it **never reproduced**
   across three fresh processes (~0.62 s each). So the anomaly is unexplained and
   I did *not* actually earn the confidence I asserted at the time. Had a slow
   first-run been real and recurring, a user running the suite once could have
   assumed it was broken. **Lesson:** isolate the slow test in the same breath as
   observing the anomaly; don't let "ran it again, it's fine" substitute for a
   root cause.

2. **Argparse `%default` bug — shipped an invalid format string.**
   I initially wrote `help="...(default: %default)"`. `%default` is not a valid
   conversion (the correct forms are `%(default)s` or `%s`), so argparse crashed
   with `TypeError: %d format: ...` on *any* invocation, including `-h`. I caught
   it only by running the CLI, and did not mentally validate the help
   interpolation before writing it. Small, but a reminder that "it compiles"
   (`py_compile`) does not exercise argparse's runtime help formatting.

3. **`path` vs `file` — I trusted a doc I had not verified.**
   I took the `get` parameter name from the qmd skill's reference doc
   (`path`, `full`) and even put `{"path":"mb-foo/bar.md","full":true}` into the
   module docstring. Against qmd 2.5.3 the real schema is `file`, `fromLine`,
   `maxLines`, `lineNumbers`. When my first live `get` call failed validation, I
   initially "corrected my test" rather than recognizing that **the source doc I'd
   copied from was itself stale** (§3). This is the most instructive miss: the
   error came from unverified prior knowledge, not from my own invention.

4. **Scope and placement decided unilaterally.**
   I chose the boundaries (no persistent SSE, no batching, tool-calls only) and
   the location (`mcp_client/` dir, single file) without checking with the user.
   "Lightweight MCP client" gave latitude and the choices are defensible, but
   they were assumptions, not confirmations. The no-persistent-stream choice in
   particular is correct *for qmd* and would be a gap for a push-based server.

5. **What went well in the process.**
   - I **ran the CLI end-to-end against the live server**, not just the unit
     tests. That is what surfaced both the argparse crash and the param-name
     error — unit tests alone would have shipped a CLI that fails on `--json`
     placement and misleads on `get` args.
   - I **re-ran anything that looked flaky** (test timing) before concluding, and
     kept the tests hermetic (in-process fake server, no network/qmd dependency).
   - I verified the exact wire protocol with `curl` *before* writing code, so the
     implementation matched observed behavior (JSON responses, the
     `mcp-session-id` header, the 202 for notifications) rather than an assumed
     one.

6. **Gaps in diligence.**
   - No **linter or type-checker** run (only `py_compile`). There is no repo
     linter config to violate, but `mypy`/`ruff` would have flagged the unused
     `status`, the `ValueError` escape, and the `tuple` annotations.
   - I did **not** consider installability (copying the client into skill dirs /
     reusing `scripts/install_common.py`). That is plausibly a later step, but it
     is currently unaddressed beyond a "next steps" mention.
   - I did **not** test against a *second* MCP server or an SSE variant with a
     leading progress notification, so the SSE path is validated only for the
     happy single-message case.

---

## 3. Cross-cutting finding (outside this client)

The **installed qmd skill's MCP reference doc is stale relative to the running
qmd 2.5.3**, and my client surfaced it because it calls the live schema.

- Doc — `~/.agents/skills/qmd/references/mcp-setup.md:81-83`:
  `get` params = `path` (string), `full` (bool?), `lineNumbers` (bool?).
- Live — qmd 2.5.3 `tools/list` for `get`:
  `file`, `fromLine`, `maxLines`, `lineNumbers` (confirmed via
  `McpClient().list_tools()`).

Consequence: anyone following the qmd skill's documented `get` parameters
(`path`, `full`) gets a `-32602 Input validation error` against qmd 2.5.3. This
predates and is independent of `mcp_client`; it lives in the separately-installed
qmd skill (from `@tobilu/qmd`), not in this repo's `skills/`. Because
task-memory-bank delegates retrieval mechanics to the qmd skill, it is worth
flagging as its own fix (either the skill doc or the qmd version is out of date).

---

## 4. Recommended follow-ups (NOT applied)

Ordered roughly by value-to-effort:

1. **Fix D1** — in `_post()`, also catch `ValueError` (and, for breadth,
   `OSError`) and raise `McpError`, so any bad `--url` yields a clean message and
   exit 1 instead of a traceback.
2. **Address D2** — add stale-session recovery: on an HTTP 400/404 whose body
   mentions the session (or, more simply, after any `McpHttpError`), reset
   `session_id`/`_connected` and retry the handshake **once**. This is the single
   most valuable change if the client is used as a persistent library. Document
   the double-`connect()`→400 behavior either way.
3. **Close D3** — add tests: a 4xx response → `McpHttpError`; an SSE body with a
   leading progress notification before the matching response; and a schemeless
   URL → `McpError` (locks in fix #1).
4. **Fix D4** — either make `McpClient` honor `MCP_URL` as its default, or scope
   the README wording to the CLI.
5. **Optional hardening** — `--header/-H` CLI flag for auth; a thread-safety note
   (or a lock) on `McpClient`; consider `.getcode()` over `.status` for the stated
   3.9+ floor; tighten the `data` error rendering to JSON.
