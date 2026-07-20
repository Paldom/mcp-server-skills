---
name: mcp-server-deployment
description: Deploys, operates, and distributes MCP servers - stateless scaling, session externalization, observability, health probes, canary rollouts, MCPB bundles, npm/PyPI packaging, MCP Registry publishing, versioning. Use when the user asks to deploy, host, scale, operate, package, publish, or version an MCP server. Not for writing server code, auth flows, hardening, or evals.
---

# mcp-server-deployment

Run and distribute an MCP server for real users. The failures this skill
fixes: in-memory session state that breaks behind a load balancer, servers
with no observability into per-tool behavior, big-bang deploys of a protocol
surface agents depend on, and "distribution" that ends at a git clone.

Registry/packaging facts verified 2026-07-20 (registry is in **preview** —
re-verify at <https://modelcontextprotocol.io/registry/> before publishing).

## When NOT to use

- Writing/fixing server code or transports → `mcp-server-implementation`
  (incl. SSE→Streamable HTTP migration).
- OAuth/token wiring → `mcp-server-auth`. Hardening/sandboxing →
  `mcp-server-security`. Evals/load-test design → `mcp-server-testing`.
- Generic web-app deployment with no MCP server involved.

## Workflow

### 1. Choose the delivery modes

| Audience | Ship as |
| --- | --- |
| Technical users, local | npm/PyPI package run over stdio (pinned install command; never `npx -y pkg@latest` in docs) |
| Non-technical users, local | **MCPB bundle** (`.mcpb`, ex-`.dxt`): zip + manifest, one-click install; mark secrets `"sensitive": true` → OS keychain |
| Multi-user / SaaS | hosted Streamable HTTP service |
| Both local + remote | one core tool layer, thin per-transport entrypoints |

### 2. Architect the remote service stateless

- App nodes hold **no** cross-request state: sessions/workflow state live in
  Redis/Postgres keyed by session id (bound to user identity), so any node
  serves any request behind a plain load balancer. Sticky sessions are a
  liability, not a strategy — and the 2026-07-28 spec revision removes
  protocol sessions entirely, so statelessness is also future-proofing.
- Modular monolith first; queue/workers behind slow or fan-out tools to keep
  p95 tool latency flat; microservices only for concrete org/scale
  boundaries.
- Serverless caveats: ~30s execution ceilings kill long tool calls (use
  progress + async patterns from `mcp-server-implementation`), and long-lived
  SSE streams need platform support. Managed MCP platforms and gateways
  (auth/rate-limit/audit termination) are legitimate shortcuts — the auth
  requirements move there, they don't disappear.

### 3. Health and rollout

- Liveness = process wedged; **readiness = real dependency health** (DB,
  cache, downstream APIs, auth discovery) — not "port open".
- Progressive delivery: canary or blue/green; at each step verify
  `initialize`, auth discovery, and one canonical `tools/call` before
  shifting more traffic. The per-request nature of Streamable HTTP makes
  canaries cheap — use them.
- Containers: slim base, non-root, pinned image tags, resource limits.

### 4. Observability per tool call

- **One structured log line + one trace span per tool invocation.** Span
  names like `tools.call.<tool_name>`; include identity/session as trace
  attributes and log fields — never as metric labels (cardinality).
- Metrics that matter: per-tool call count, latency percentiles, error rate,
  `isError` rate, active streams/sessions, downstream latency, token/cost
  counters where billable.
- Alert on: sustained 5xx, auth-discovery failures, tool timeout spikes,
  readiness drops, per-caller cost anomalies. Behavioral anomalies (guardrail
  blocks, weird session lengths) are the security signal —
  `mcp-server-security` consumes these.
- OpenTelemetry end-to-end; logs redact secrets/PII (audit-store rules live
  in `mcp-server-security`).

### 5. Package for local install

MCPB: manifest + server files zipped; supports Node/Python/binary; Claude
Desktop bundles a Node runtime; secrets marked `"sensitive"` are stored in
the OS keychain. Keep the manifest's env/config schema minimal and validated
at startup. For npm/PyPI: ship an executable entrypoint (`npx your-server` /
`uvx your-server`), document the exact pinned client-config JSON, and keep
tool code per-call self-contained so a misconfigured install can still start
and list tools (users see the config error at call time, not a dead server).
Server docs ship with the package: every tool documented with at least a few
working invocation examples, required permissions/scopes, and rate limits.

### 6. Publish to the MCP Registry

```bash
brew install mcp-publisher            # or the release binary
mcp-publisher init                    # scaffolds server.json
mcp-publisher login github            # verifies the io.github.* namespace
mcp-publisher publish
```

`server.json` (schema: static.modelcontextprotocol.io) points at your
packages (npm/PyPI/Docker) and/or `remotes` URL; npm packages must carry a
matching `mcpName` field in package.json for verification; custom-domain
namespaces verify via DNS/HTTP challenge. The registry hosts **metadata
only**, is consumed by downstream sub-registries, does not security-review
listings, and is in preview — expect possible breaking changes.
`python3 "${CLAUDE_SKILL_DIR}/scripts/check_server_json.py" server.json`
gates the manifest before publishing.

### 7. Version without breaking clients

- Server/package: **semver** — breaking tool-interface change = major.
- Protocol: date-based revisions negotiated per session; support the current
  revision plus what your real clients need; send/expect
  `MCP-Protocol-Version` correctly (mechanics in `mcp-server-implementation`).
- Tool surface stability: additive fields over renames; deprecate with a
  notice window in tool descriptions (agents read them) before removal;
  schema-snapshot diff in CI (`mcp-server-testing`) catches accidents.
- Keep a README compatibility note: protocol revisions supported, clients
  tested, SDK version.

## Output spec

A production deployment: stateless nodes with externalized state; readiness
gated on real dependencies; canary rollout verifying init/auth/tool-call;
per-tool logs+spans+metrics with low-cardinality labels and actionable
alerts; local packages (npm/PyPI and/or MCPB) with pinned install docs;
registry entry published from a validated `server.json` under a verified
namespace; semver + protocol compatibility note in the README.

## Gotchas

- In-memory session state is the #1 horizontal-scaling breaker — externalize
  before adding replicas, or go stateless and skip sessions entirely.
- Client configs pinned to `@latest` re-introduce the supply-chain risk your
  pinning removed — pin in docs and MCPB manifests too.
- Registry preview status is real: entries/data may reset before GA; don't
  make the registry your only distribution channel.
- Corporate proxies and some LBs buffer or kill long-lived SSE — test the GET
  stream through the real ingress path, enable heartbeats, and prefer JSON
  response mode where streams aren't needed.
- A gateway that terminates auth/ratelimits does not exempt the server from
  validating what reaches it — defense in depth, not delegation.

## Pointers

- `references/operations.md` — reference architecture, probe/rollout/OTel
  examples, MCPB manifest anatomy, server.json anatomy, gateway pattern,
  versioning matrix template.
- `scripts/check_server_json.py` — deterministic registry-manifest gate.
