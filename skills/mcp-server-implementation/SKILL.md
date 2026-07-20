---
name: mcp-server-implementation
description: Implements MCP servers with the official TypeScript or Python SDK - registering tools/resources/prompts, stdio and Streamable HTTP transports, lifecycle, isError vs protocol errors, structured output, progress and cancellation. Use when the user asks to build, create, code, scaffold, or debug an MCP server or its transport. Not for choosing the tool surface, OAuth, hardening, evals, or hosting.
---

# mcp-server-implementation

Write the MCP server code: SDK setup, primitive registration, transport wiring,
error semantics, and protocol behavior. Fixes the failures agents actually hit:
stale/deprecated SDK APIs, stdout-corrupted stdio streams, exceptions where
`isError` results belong, hand-rolled framing, and transport wiring that breaks
in real clients.

Targets spec revision **2025-11-25** and SDKs verified current on 2026-07-20:
TypeScript `@modelcontextprotocol/sdk` **v1.29** and Python `mcp` **v1.28**
(pins below). Re-verify at <https://modelcontextprotocol.io/docs/sdk> if months
have passed — v2 SDKs targeting the 2026-07-28 spec revision are in beta.

## When NOT to use

- Deciding what tools/resources/prompts to expose → `mcp-server-design` (do it
  first; coding an undesigned surface produces API-wrapper servers).
- OAuth/token validation → `mcp-server-auth`. Threats/hardening →
  `mcp-server-security`. Evals/Inspector deep-dives → `mcp-server-testing`.
  Hosting/packaging/registry → `mcp-server-deployment`.
- Building MCP *clients*/hosts, or generic non-MCP servers.

## Workflow

### 1. Preconditions

Surface designed (tool list, schemas, descriptions — else apply
`mcp-server-design`). Pick the language: TypeScript or Python cover most cases
(Tier 1 SDKs, best docs); C#/Go also Tier 1; Java/Rust Tier 2. Pick the
transport by deployment target: **stdio** for a local subprocess of one client,
**Streamable HTTP** for anything remote/multi-client. Wrong transport choice is
a rewrite, not a config flag.

### 2. Project setup — pinned

Python (official SDK; its high-level API is the bundled `FastMCP` class — NOT
the third-party `fastmcp`/jlowin package):

```bash
uv add "mcp[cli]>=1.27,<2"        # or: pip install "mcp[cli]>=1.27,<2"
```

TypeScript (v1 is the production line; required peer dep `zod`):

```bash
npm i @modelcontextprotocol/sdk@^1.29 zod && npm i -D typescript @types/node
```

Never invoke servers with unpinned `npx package@latest` — a dependency that
starts printing a banner to stdout kills every stdio install downstream.

### 3. Build shared infrastructure first

One HTTP/API client with timeouts, one centralized error mapper
(404/403/429/timeout → specific, recovery-oriented strings), shared
pagination/formatting helpers — then register tools against them. Copy-pasted
per-tool fetch/error code is the main source of inconsistent agent-facing
behavior. All I/O async (httpx / native fetch or axios); validate env config at
startup and exit non-zero with a clear message when missing.

### 4. Register primitives with current APIs

Per-language walkthroughs with complete code: `references/python-server.md`,
`references/typescript-server.md`. The load-bearing rules:

- **Python**: `FastMCP(name)`; `@mcp.tool()` (schema inferred from type hints +
  docstring, or explicit Pydantic models with `extra="forbid"`),
  `@mcp.resource("scheme://{param}")`, `@mcp.prompt()`. `Context` injection
  gives `ctx.report_progress`, `ctx.info/debug/error` (protocol logging),
  `ctx.elicit`, lifespan state.
- **TypeScript**: `new McpServer({name, version})` +
  `server.registerTool(name, config, handler)` / `registerResource` /
  `registerPrompt` with zod schemas. The older `server.tool()` and raw
  `setRequestHandler` styles work but are legacy; use `register*` in new code.
- Declare only capabilities you implement (`tools.listChanged` only if you
  actually emit `notifications/tools/list_changed`, etc.). Invoking an
  un-negotiated feature is a protocol violation.
- Tool names/schemas/descriptions come from the design doc; schema dialect
  defaults to JSON Schema 2020-12; `inputSchema` must never be null.

### 5. Wire the transport

**stdio** — the client spawns you; stdin/stdout carry newline-delimited
JSON-RPC. THE RULE: **nothing but MCP messages on stdout, ever.** One stray
`print()` / `console.log()` / dependency banner corrupts framing and the client
drops the connection — works-in-terminal-fails-in-client is the signature.
Route all logging to stderr (spec-legal for any log level) or files. Run
`scripts/check_stdio_hygiene.py` over the source tree to gate this. Credentials
come from the environment, not an OAuth flow.

**Streamable HTTP** — one endpoint (e.g. `/mcp`): every client message is a new
POST with `Accept: application/json, text/event-stream`; the server answers
with a single JSON body or an SSE stream (client must support both); GET opens
the optional server-push stream. Mechanics you must get right (details +
wiring code in `references/streamable-http.md`):

- `MCP-Protocol-Version` header on post-initialize requests; absent → assume
  2025-03-26; unsupported → 400.
- Sessions are optional: `Mcp-Session-Id` issued on the InitializeResult;
  treat it as a **lookup key** (externalizable to Redis/DB), never as
  authentication; missing → 400, expired → 404 (client re-initializes).
- Resumability via SSE event IDs + `Last-Event-ID` on GET; IDs unique per
  session; never replay across streams.
- Security floor even without auth: validate `Origin` (invalid → **403**,
  DNS-rebinding defense), bind `127.0.0.1` for local servers.
- Old HTTP+SSE (two-endpoint, 2024-11-05) is deprecated since revision
  2025-03-26 — migrate; optionally serve both during a window.

### 6. Error semantics — two distinct layers

- **Protocol errors** (JSON-RPC error responses, e.g. `-32602`): unknown tool,
  malformed request — the tool never ran.
- **Execution errors**: return a normal result with `isError: true` and a
  recovery-oriented message in `content`. The *model* reads this and
  self-corrects. Since 2025-11-25 (SEP-1303) input-validation failures belong
  here too, not in protocol errors. Never leak stack traces; never let an
  unhandled exception escape a handler.

### 7. Structured output

Declare `outputSchema`; return `structuredContent` (SDKs validate against the
schema) **plus** the same data serialized in a text content block for
backward compatibility. Keep them consistent — divergence is a common bug.
Known sharp edge: some SDK versions validate `structuredContent` against
`outputSchema` even on `isError` results — test your error path.

### 8. Long-running work

Requests have client timeouts; serverless platforms add ~30s ceilings. For
anything slow: emit `notifications/progress` against the request's
`progressToken` (rate-limited; stop after completion), honor
`notifications/cancelled` (clean up; the response/cancel race is normal). The
**tasks** feature (SEP-1686) is experimental in 2025-11-25 and moves to an
extension in the next revision — gate any use behind its capability and say so.

### 9. Server→client features — capability-gate everything

`ctx.elicit` / `elicitInput` (ask the user mid-tool), sampling (ask the
client's LLM), roots — all require the client to declare the capability, and
client support is thin (verify your target clients). Secrets/credentials MUST
NOT be collected via form elicitation — 2025-11-25 adds URL mode for that.
**RC horizon**: the 2026-07-28 revision deprecates roots/sampling/logging and
replaces server-initiated requests with a retry pattern (MRTR) — prefer tool
parameters and stderr/OTel logging over deep investment in these.

### 10. Verify

Build gates: `npm run build` / `python -m py_compile` + server starts. Then
launch MCP Inspector against it (`npx @modelcontextprotocol/inspector <cmd>`,
or `uv run mcp dev server.py`) and exercise every tool, including one error
path each. Full test/eval methodology: `mcp-server-testing`.

## Output spec

A running server: pinned deps; shared client/error/pagination infra; primitives
registered with current APIs; transport wired per the rules above (stdio
hygiene script passes, or HTTP endpoint validates Origin/version headers);
errors split protocol-vs-`isError`; structured output consistent; logs on
stderr or protocol logging; env-validated config; verified in Inspector.

## Gotchas

- **The stdout rule is absolute** under stdio — including dependencies'
  banners and deprecation warnings. Grep them all; the failure is silent.
- **JSON-RPC batching was removed** in 2025-06-18 — never send/expect batches;
  batch inside tool semantics instead.
- Version negotiation is strict: respond to `initialize` with the client's
  version or your latest supported; mismatched clients disconnect. Wait for
  `notifications/initialized` before server-initiated traffic.
- The two FastMCPs: official SDK's bundled `FastMCP` ≠ third-party
  `fastmcp` (jlowin) / `punkpeye/fastmcp` (TS). This skill uses official only.
- v2 SDK betas (TS split packages `@modelcontextprotocol/server`+`/client`;
  Python renames `FastMCP`→`MCPServer`) target the 2026-07-28 spec — migration
  material, not production defaults; a `v1-to-v2` codemod exists for TS.
- stdio servers inherit the client's spawn environment — a config with a bare
  `python` or missing `PATH` fails only inside GUI clients; use absolute paths.
- Empty result sets must still return a well-formed result (clients hang on
  nothing); return "no results found" text, not null.

## Pointers

- `references/python-server.md` — complete FastMCP server (tools/resources/
  prompts, Context, structured output, lifespan, both transports).
- `references/typescript-server.md` — complete `McpServer` server (registerTool
  + zod, structured output, both transports, express wiring).
- `references/streamable-http.md` — wire-level transport + lifecycle contract
  (headers, sessions, resumability, SSE polling, migration, RC horizon).
- `scripts/check_stdio_hygiene.py` — greps a source tree for stdout writes that
  corrupt stdio framing; non-zero exit on findings.
