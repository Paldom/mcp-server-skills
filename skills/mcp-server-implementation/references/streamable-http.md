# Wire contract: lifecycle + Streamable HTTP (spec 2025-11-25)

Every claim verified against the official spec pages on 2026-07-20
(<https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle> and
`/basic/transports`). SDKs implement most of this; you still own the
security-relevant parts and the deployment behavior.

**Contents:** [Lifecycle](#lifecycle) · [stdio rules](#stdio-rules) ·
[Streamable HTTP rules](#streamable-http-rules) · [Sessions](#sessions) ·
[Resumability & SSE polling](#resumability--sse-polling) ·
[Migrating off HTTP+SSE](#migrating-off-httpsse) ·
[2026-07-28 horizon](#2026-07-28-horizon)

## Lifecycle

1. Client sends `initialize` (its `protocolVersion`, capabilities, clientInfo).
   It MUST be the first interaction; do not cancel it.
2. Server responds with the same version if supported, else its own latest;
   plus its capabilities, `serverInfo`, and optional `instructions` (a usage
   manual the host may feed the model — write one).
3. Client sends `notifications/initialized`. Only then start normal traffic.
4. Shutdown has no protocol message: stdio = client closes stdin (then SIGTERM,
   SIGKILL); HTTP = close connections. Handle abrupt death gracefully.

Capabilities you declare must be real: `tools.listChanged` implies you emit
`notifications/tools/list_changed`; `resources.subscribe` implies you handle
`resources/subscribe`. Invoking un-negotiated features is a protocol violation.
Timeouts: enforce per-request timeouts both directions; progress notifications
MAY reset the clock but keep an absolute maximum.

## stdio rules

- Messages are newline-delimited JSON-RPC over stdin/stdout, UTF-8, no embedded
  newlines.
- stdout carries **only** MCP messages. stderr may carry any logging (any
  level — broadened in 2025-11-25); clients may capture or ignore it.
- Credentials via environment variables; the OAuth authorization spec is
  explicitly not for stdio.
- The client spawns you: absolute paths in client configs; the environment is
  the client's, not your shell's.

## Streamable HTTP rules

One MCP endpoint (e.g. `https://host/mcp`) supporting POST and GET.

| Rule | Detail |
| --- | --- |
| POST per message | every client JSON-RPC message is a new POST with `Accept: application/json, text/event-stream` |
| Response forms | server returns one JSON object (`application/json`) **or** an SSE stream (`text/event-stream`); clients must support both. Notifications/responses POSTed by the client → `202 Accepted`, no body |
| GET stream | opens the optional server→client push stream; server MUST return SSE or 405 |
| `MCP-Protocol-Version` header | client sends it on every post-initialize request; absent → server SHOULD assume `2025-03-26`; invalid/unsupported → 400 |
| Origin validation | servers MUST validate `Origin`; invalid → **403** (MUST, new in 2025-11-25). This is the DNS-rebinding defense — do it even on unauthenticated local servers |
| Local binding | bind `127.0.0.1`, not `0.0.0.0`, for localhost servers |
| Auth | SHOULD authenticate all remote connections — `mcp-server-auth` |

## Sessions

Optional. If you issue `Mcp-Session-Id` on the InitializeResult (visible ASCII,
cryptographically secure):

- Client MUST echo it on all subsequent requests; request without it → 400.
- Expired/terminated session → 404; the client then re-initializes.
- Client SHOULD send HTTP DELETE to end a session (405 if you don't allow it).
- Sessions are **routing/lookup state, never authentication** (hard spec MUST
  NOT). Authorization rides the `Authorization` header on every request.
- For horizontal scaling keep session state in Redis/Postgres keyed by
  session id (bind keys to user identity: `user_id:session_id`) so any node
  serves any request — see `mcp-server-deployment`.

Prefer the stateless pattern (no session ids) unless you have real
cross-request state: less to secure, nothing to externalize, and it matches
where the protocol is going.

## Resumability & SSE polling

- Attach `id` fields to SSE events; IDs are unique per session and encode the
  stream they belong to.
- Client resumes by GET + `Last-Event-ID`; replay only messages from that
  stream, never another's.
- Disconnect ≠ cancellation: a dropped stream means retry/resume, not abort;
  cancellation is only `notifications/cancelled`.
- SSE polling (2025-11-25, SEP-1699): server SHOULD send a primer event
  immediately (event id + empty data), MAY close the connection at will
  (SHOULD send `retry` first); clients poll by reconnecting.

## Migrating off HTTP+SSE

The 2024-11-05 two-endpoint HTTP+SSE transport is deprecated since revision
**2025-03-26** (formally Deprecated in the lifecycle registry; vendors are
setting hard shutdown dates). Migration:

1. Stand up the single Streamable HTTP endpoint.
2. Optionally keep the old `/sse` + message endpoints alongside during a
   window; clients auto-detect by POSTing an InitializeRequest to the new
   endpoint and falling back to GET-expecting-`endpoint`-event on 4xx.
3. Announce a shutdown date; delete the legacy path.

## 2026-07-28 horizon

The next revision (release candidate at authoring time; verify at
<https://modelcontextprotocol.io/specification/draft/changelog>) is the largest
since launch. Nothing switches off for 2025-11-25 implementations on that date
(deprecated features stay ≥12 months), but design new servers so the moves are
cheap:

- **Stateless core**: `initialize` handshake and protocol-level sessions
  (`Mcp-Session-Id`) removed; version/capabilities travel per-request in
  `_meta`; new required `server/discover` RPC; SSE resumability removed
  (broken stream = re-issue the request).
- **Server-initiated requests replaced by MRTR** (`resultType:
  "input_required"` + client retry); roots/sampling/logging deprecated —
  prefer tool parameters, direct LLM APIs, and stderr/OTel logging today.
- Subscriptions move to a single long-lived `subscriptions/listen` POST
  stream; `ping` and `logging/setLevel` removed; new `Mcp-Method`/`Mcp-Name`
  headers; caching metadata (`ttlMs`, `cacheScope`) on list results.
- Tasks moves from experimental core to the `io.modelcontextprotocol/tasks`
  extension.

Practical translation: keep servers stateless where possible, don't couple new
code to protocol sessions or server-initiated requests, and pin the spec
revision you target in your README.
