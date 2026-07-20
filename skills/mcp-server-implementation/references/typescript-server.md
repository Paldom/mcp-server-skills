# TypeScript MCP server — official SDK (`@modelcontextprotocol/sdk` v1.29 line)

APIs verified against the official typescript-sdk README/source at v1.29.0
(2026-07-20). Production pin: `^1.29`; peer dep `zod`. The v2 beta splits the
SDK into `@modelcontextprotocol/server` + `/client` for the 2026-07-28 spec —
a `npx @modelcontextprotocol/codemod@beta v1-to-v2 .` codemod exists; treat v2
as migration material, not the default. Concepts overlap Anthropic's
`mcp-builder` skill (Apache-2.0), rewritten and re-verified.

**Contents:** [Project setup](#project-setup) · [Minimal server](#minimal-server) ·
[Tools with zod](#tools-with-zod) · [Structured output](#structured-output--errors) ·
[Resources & prompts](#resources--prompts) · [Transports](#transports) ·
[Checklist](#checklist)

## Project setup

```bash
npm i @modelcontextprotocol/sdk@^1.29 zod
npm i -D typescript @types/node
```

`tsconfig.json`: `"strict": true`, `"module": "Node16"`, `"target": "ES2022"`.
Layout that scales: `src/index.ts` (entry), `src/tools/`, `src/services/`
(shared API client), `src/schemas.ts`. Build must pass (`tsc`) before any
Inspector run. No `any`; derive types with `z.infer`.

## Minimal server

```typescript
// src/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "tickets", version: "1.0.0" });

server.registerTool(
  "tickets_search",
  {
    title: "Search tickets",
    description:
      "Search tickets by free-text query. Use when the user asks to find or " +
      "list tickets. Not for creating tickets (tickets_create). " +
      "Returns id, title, status, assignee, newest first.",
    inputSchema: {
      query: z.string().describe("Free-text search query"),
      limit: z.number().int().min(1).max(50).default(20),
    },
    annotations: { readOnlyHint: true },
  },
  async ({ query, limit }) => {
    const items = await api.searchTickets(query, limit); // one shared client
    return { content: [{ type: "text", text: renderMarkdown(items) }] };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("tickets MCP server running on stdio"); // stderr ONLY — never console.log
```

`inputSchema` takes a **zod raw shape** (object of zod validators); `.describe()`
strings double as model-facing parameter docs. Reject unknown fields where
strictness matters. JSDoc comments are NOT extracted — everything the model
needs goes in `description`/`.describe()`.

## Tools with zod

```typescript
const SearchShape = {
  email: z.string().email().describe("Customer email address"),
  status: z.enum(["pending", "shipped", "delivered", "cancelled"]).default("pending"),
  limit: z.number().int().min(1).max(50).default(20),
  cursor: z.string().optional().describe("Opaque cursor from a previous page"),
  response_format: z.enum(["concise", "detailed"]).default("concise"),
};
```

Shared infrastructure first: one API client module with timeouts, one
`mapHttpError(status): string` returning recovery-oriented messages
(404 → "not found; call X to list valid IDs", 429 → "rate limited; retry after
Ns"), shared pagination helpers, a module-level `CHARACTER_LIMIT` (in characters —
size it well under client-side token caps, which run ~25k tokens) that
truncates oversized responses **with a note telling the agent how to fetch the
rest**.

## Structured output & errors

```typescript
server.registerTool(
  "weather_get_forecast",
  {
    description: "Get the forecast for a city. Returns structured daily data.",
    inputSchema: { city: z.string() },
    outputSchema: {                       // declared → clients validate
      city: z.string(),
      days: z.array(z.object({ date: z.string(), high_c: z.number(), low_c: z.number() })),
    },
  },
  async ({ city }) => {
    try {
      const data = await api.forecast(city);
      const structured = { city, days: data.days };
      return {
        structuredContent: structured,                      // machine-readable
        content: [{ type: "text", text: JSON.stringify(structured) }], // back-compat
      };
    } catch (e) {
      return {
        isError: true,                                      // model-visible failure
        content: [{ type: "text", text:
          `City '${city}' not found. Use full city names ("Paris", not "paris, fr").` }],
      };
    }
  },
);
```

Rules: `structuredContent` must conform to `outputSchema` and stay consistent
with the text block; execution failures are `isError: true` results (including
input-validation failures per SEP-1303), protocol errors stay the SDK's
business; never leak stack traces; test the error path when `outputSchema` is
declared (some SDK versions validate it even on errors).

## Resources & prompts

```typescript
import { ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";

server.registerResource(
  "orders-schema",
  "schema://orders",
  { title: "Orders schema", description: "Read-only reference schema", mimeType: "text/markdown" },
  async (uri) => ({ contents: [{ uri: uri.href, text: ORDERS_SCHEMA_MD }] }),
);

server.registerResource(
  "ticket",
  new ResourceTemplate("tickets://{ticketId}", { list: undefined }),
  { title: "Ticket", description: "One ticket by ID" },
  async (uri, { ticketId }) => ({ contents: [{ uri: uri.href, text: await getTicket(ticketId) }] }),
);

server.registerPrompt(
  "investigate_incident",
  { title: "Investigate incident", description: "SOP: triage an incident",
    argsSchema: { service: z.string() } },
  ({ service }) => ({ messages: [{ role: "user",
    content: { type: "text", text: `Check ${service} alerts, recent deploys, error logs...` } }] }),
);
```

Use `register*` APIs in new code; `server.tool()` / raw `setRequestHandler`
are the legacy style (reach for the low-level `Server` class only when you
need protocol-level control).

## Transports

stdio: as in the minimal server. The stdout rule is absolute — audit
dependencies for `console.log` too (`scripts/check_stdio_hygiene.py`).

Streamable HTTP, stateless pattern (scales behind plain load balancers; the
direction the 2026-07-28 revision pushes everyone):

```typescript
import express from "express";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

const app = express();
app.use(express.json());

app.post("/mcp", async (req, res) => {
  // per-request server+transport = no shared state between requests
  const server = buildServer();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,   // stateless: no Mcp-Session-Id issued
    enableJsonResponse: true,        // plain JSON instead of SSE when possible
  });
  res.on("close", () => { void transport.close(); void server.close(); });
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(3000, "127.0.0.1");       // localhost bind for local; see below for remote
```

Wire contract you still own (see `streamable-http.md`): validate `Origin`
(invalid → 403), handle `MCP-Protocol-Version`, and — if you opt into stateful
sessions with `sessionIdGenerator` — treat session ids as lookup keys, never
authentication. Remote servers add OAuth: `mcp-server-auth`.

## Checklist

- [ ] SDK `^1.29` + zod pinned; `tsc` strict build passes
- [ ] `register*` APIs only; descriptions carry when-to-use + param docs
- [ ] zero stdout writes under stdio (`check_stdio_hygiene.py` clean)
- [ ] shared API client / error mapper / `CHARACTER_LIMIT` truncation
- [ ] `outputSchema` + `structuredContent` consistent; error path tested
- [ ] lists paginated; empty results return explanatory text, not nothing
- [ ] env config validated at startup; Inspector run incl. error paths
