# Python MCP server — official SDK (`mcp` v1.28 line)

APIs verified against the official python-sdk README at v1.28.1 (2026-07-20).
Production pin: `mcp>=1.27,<2`. The v2 beta (`2.0.0b*`) targets the 2026-07-28
spec and renames `FastMCP` → `MCPServer` — migration material, not a default.
Concepts here overlap Anthropic's `mcp-builder` skill (Apache-2.0), rewritten
and re-verified.

**Contents:** [Minimal server](#minimal-server) · [Tools](#tools-done-well) ·
[Structured output](#structured-output) · [Errors](#errors) ·
[Resources & prompts](#resources--prompts) · [Context](#context-progress-logging-elicitation) ·
[Lifespan](#lifespan-shared-connections) · [Transports](#running-transports) ·
[Checklist](#checklist)

## Minimal server

```python
# server.py
import sys
import logging
from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO)  # NEVER stdout
mcp = FastMCP("tickets")

@mcp.tool()
def tickets_search(query: str, limit: int = 20) -> str:
    """Search tickets by free-text query.

    Use when the user asks to find, list, or look up tickets.
    Not for creating tickets (use tickets_create).
    Returns a markdown list: id, title, status, assignee.
    """
    ...

if __name__ == "__main__":
    mcp.run()          # stdio by default
```

Dev loop: `uv run mcp dev server.py` opens MCP Inspector against it.
Claude Code: `claude mcp add tickets -- uv run --directory /abs/path python server.py`
(stdio; for HTTP servers: `claude mcp add --transport http tickets http://localhost:8000/mcp`).

## Tools done well

Schema comes from type hints + docstring; constrain with `Literal`, defaults,
and Pydantic models when you need validation rules:

```python
from typing import Literal
from pydantic import BaseModel, Field

class SearchArgs(BaseModel):
    model_config = {"extra": "forbid"}          # reject unknown fields
    email: str = Field(description="Customer email address")
    status: Literal["pending", "shipped", "delivered", "cancelled"] = "pending"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, description="Opaque cursor from a previous page")
    response_format: Literal["concise", "detailed"] = "concise"

@mcp.tool()
async def orders_search(args: SearchArgs) -> dict:
    """Search a customer's orders. Use for order status questions.
    Not for refunds (orders_refund). Returns items, has_more, next_cursor."""
    page = await api.search_orders(args)        # one shared API client
    return {"items": page.items, "has_more": page.has_more,
            "next_cursor": page.next_cursor}
```

Share one `httpx.AsyncClient` (timeouts set) and one error-mapper across all
tools — per-tool copies drift. All I/O `async`.

## Structured output

Return a typed value (TypedDict / dataclass / Pydantic model / typed dict) and
FastMCP generates `outputSchema` and returns `structuredContent` plus the
serialized text block automatically. Keep the return type stable — clients
validate against the schema. Test the error path: some SDK versions validate
`structuredContent` before honoring `isError`.

## Errors

```python
from mcp.server.fastmcp.exceptions import ToolError

@mcp.tool()
async def orders_get(order_id: str) -> dict:
    """Fetch one order by ID. Returns full order JSON."""
    try:
        return await api.get_order(order_id)
    except OrderNotFound:
        # ToolError -> isError result: the MODEL reads this and self-corrects.
        raise ToolError(
            f"Order '{order_id}' not found. Call orders_search(email=...) "
            "to list valid order IDs.")
```

Do NOT return a hand-built `{"isError": true, ...}` dict — FastMCP serializes
it as ordinary (structured) output without setting the protocol flag. Raise
`ToolError` with a recovery message, or return a full `CallToolResult` when
you need to control content blocks. Unhandled exceptions also become `isError`
results, but as a bare `"Error executing tool <name>: <str(e)>"` — always
catch and rewrite into a recovery instruction. Input-validation failures are
returned as `isError` results too (SEP-1303, 2025-11-25). Protocol errors
(unknown tool, malformed JSON-RPC) are the SDK's job, not yours.

## Resources & prompts

```python
@mcp.resource("schema://orders")
def orders_schema() -> str:
    """Read-only reference schema for the orders domain."""
    return ORDERS_SCHEMA_MARKDOWN

@mcp.resource("tickets://{ticket_id}")           # RFC 6570 template
def ticket(ticket_id: str) -> str:
    return get_ticket_markdown(ticket_id)

@mcp.prompt()
def investigate_incident(service: str) -> str:
    """SOP: triage an incident end to end."""
    return f"Check {service} alerts, then recent deploys, then error logs..."
```

Resources are application-controlled read-only context; client support is
uneven — verify your target clients (see `mcp-server-design` for the
primitive decision).

## Context: progress, logging, elicitation

Add a `Context` parameter to receive per-request capabilities:

```python
from mcp.server.fastmcp import Context

@mcp.tool()
async def data_export(dataset: str, ctx: Context) -> str:
    """Export a dataset. May take minutes; reports progress."""
    total = await api.count(dataset)
    for i, chunk in enumerate(api.iter_chunks(dataset)):
        await process(chunk)
        await ctx.report_progress(i + 1, total)      # rate-limit yourself
        await ctx.info(f"chunk {i + 1}/{total}")     # protocol logging, not print()
    return "export complete: s3://bucket/export.parquet"
```

`ctx.elicit(...)` asks the connected user for input mid-tool — capability-gate
it (many clients don't support elicitation) and NEVER collect secrets through
form elicitation (2025-11-25 requires URL mode for credentials). RC horizon:
server-initiated requests are reworked (MRTR) and sampling/roots/logging are
deprecated in the 2026-07-28 revision — don't build deep dependencies on them.

## Lifespan: shared connections

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(server):
    db = await Database.connect(os.environ["DATABASE_URL"])
    try:
        yield {"db": db}
    finally:
        await db.close()

mcp = FastMCP("tickets", lifespan=lifespan)
# in a tool: db = ctx.request_context.lifespan_context["db"]
```

Validate required env vars at startup; exit non-zero with a clear message when
missing (a server that half-starts is worse than one that fails loudly).

## Running: transports

```python
mcp.run()                                  # stdio (local, default)
mcp.run(transport="streamable-http")       # remote; serves POST/GET /mcp
```

For Streamable HTTP also enforce the wire contract (Origin validation → 403,
`MCP-Protocol-Version` handling, optional session ids as lookup keys only) —
see `streamable-http.md` in this folder. Auth for remote servers:
`mcp-server-auth`.

## Checklist

- [ ] `mcp>=1.27,<2` pinned; official SDK (not third-party `fastmcp`)
- [ ] zero stdout writes (run `scripts/check_stdio_hygiene.py`)
- [ ] shared API client + error mapper; all I/O async with timeouts
- [ ] every tool: typed constrained params, when-to-use docstring, pagination
      on lists, `isError` + recovery text on failure
- [ ] structured returns stable; error path tested with `outputSchema`
- [ ] env config validated at startup; secrets never hardcoded
- [ ] verified in Inspector (`uv run mcp dev server.py`), including error paths
