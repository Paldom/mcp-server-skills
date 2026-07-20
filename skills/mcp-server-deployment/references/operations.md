# MCP server operations — reference configurations

Verified 2026-07-20; registry facts from <https://modelcontextprotocol.io/registry/>
(preview — re-verify before publishing).

**Contents:** [Reference architecture](#reference-architecture) ·
[Probes & rollout](#probes--rollout) · [Observability](#observability) ·
[MCPB manifest anatomy](#mcpb-manifest-anatomy) ·
[server.json anatomy](#serverjson-anatomy) · [Gateway pattern](#gateway-pattern) ·
[Compatibility matrix template](#compatibility-matrix-template)

## Reference architecture

```
Agent/Host → Ingress (TLS, WAF) → Auth layer (OAuth RS validation)
          → MCP service, N stateless nodes
               ├── Postgres   durable state, audit pointers
               ├── Redis      sessions (user-bound keys), rate limits, cache
               ├── Queue → workers   slow/fan-out tools
               └── OTel collector → traces/metrics/logs
```

Modular monolith until org/scale boundaries force a split. The MCP-facing
service stays thin: protocol handling, authz, validation, quotas,
orchestration; heavy work goes behind the queue so tool p95 stays flat.

Session key discipline: `session:{user_id}:{session_id}` — bound to identity
(hijack containment), TTL'd, survives node death. With no cross-request state,
skip sessions entirely (`sessionIdGenerator: undefined` in the TS SDK).

## Probes & rollout

```yaml
livenessProbe:  { httpGet: { path: /health/live,  port: 8080 }, periodSeconds: 10 }
readinessProbe: { httpGet: { path: /health/ready, port: 8080 }, periodSeconds: 5 }
startupProbe:   { httpGet: { path: /health/start, port: 8080 }, failureThreshold: 30, periodSeconds: 5 }
```

`/health/ready` returns 200 only when DB/cache/critical downstreams answer and
auth discovery would succeed. Canary (Argo Rollouts shape):

```yaml
strategy:
  canary:
    steps:
      - setWeight: 10
      - pause: { duration: 5m }    # verify: initialize, PRM fetch, canonical tools/call
      - setWeight: 50
      - pause: { duration: 10m }
```

Verification at each pause is a scripted client run, not a dashboard glance:
initialize → discovery → one representative `tools/call` → assert result.

## Observability

Per tool call: one span (`tools.call.orders_search`) with attributes
`mcp.tool`, `mcp.session_id`, `user.id`, `mcp.is_error`, downstream spans
nested; one structured log line with the same correlation IDs, secrets/PII
redacted. Metrics (low cardinality — tool name yes, user id no):

| Metric | Type | Alert when |
| --- | --- | --- |
| `mcp_tool_calls_total{tool,outcome}` | counter | error ratio sustained ↑ |
| `mcp_tool_latency_seconds{tool}` | histogram | p95 over SLO |
| `mcp_active_streams` | gauge | saturation |
| `auth_discovery_failures_total` | counter | > 0 sustained |
| `readiness` | gauge | drops |
| `mcp_tool_cost_units{tool}` | counter | per-caller anomaly (security signal) |

The 2026-07-28 revision standardizes OTel context propagation in `_meta`
(`traceparent`/`tracestate`) — align span plumbing with W3C trace context now.

## MCPB manifest anatomy

`.mcpb` = zip(server files + `manifest.json`). Build:
`npm i -g @anthropic-ai/mcpb && mcpb init && mcpb pack`. Manifest carries:
name/version/description, entrypoint + runtime (node/python/binary; Claude
Desktop ships a Node runtime), and `user_config` fields — mark credentials:

```json
"user_config": {
  "api_key": { "type": "string", "title": "API key",
               "sensitive": true, "required": true }
}
```

`"sensitive": true` → stored in the OS keychain (macOS Keychain / Windows
Credential Manager), not plaintext config. Validate config at startup; keep
tool calls self-contained (connect per-call) so a misconfigured install still
starts and lists tools.

## server.json anatomy

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.acme/tickets",
  "description": "Search and manage Acme tickets from any MCP client.",
  "repository": { "url": "https://github.com/acme/tickets-mcp", "source": "github" },
  "version": "1.2.0",
  "packages": [
    { "registryType": "npm", "identifier": "@acme/tickets-mcp", "version": "1.2.0",
      "transport": { "type": "stdio" },
      "environmentVariables": [
        { "name": "ACME_API_KEY", "description": "API key", "isRequired": true, "isSecret": true } ] }
  ],
  "remotes": [ { "type": "streamable-http", "url": "https://mcp.acme.com/mcp" } ]
}
```

- Namespace ownership is verified: `io.github.<user>/**` via GitHub login in
  `mcp-publisher login github`; custom reverse-DNS via DNS/HTTP challenge.
- npm package must include `"mcpName": "io.github.acme/tickets"` in its
  package.json (NuGet: an `mcp-name` marker in the README) or verification
  fails.
- Publish flow: `mcp-publisher init` → edit → `login` → `publish`; the
  registry stores metadata only and syncs to sub-registries (GitHub's, etc.).
- Schema URL carries a date — check for a newer schema before publishing.

## Gateway pattern

Running several servers for one org? An MCP gateway (reverse proxy +
catalog) gives a single entry point with central auth termination, rate
limits, audit, kill switches, and transport translation. The servers behind
it still validate what reaches them (defense in depth). Commercial and OSS
gateways exist; evaluate against: OAuth RS conformance, per-tool policy,
audit export, and description-drift detection.

## Compatibility matrix template

| Server version | Protocol revisions | SDKs | Clients tested |
| --- | --- | --- | --- |
| 1.2.x | 2025-11-25, 2025-06-18 | mcp 1.28 / TS SDK 1.29 | Claude Code, Claude Desktop, VS Code |
| 1.1.x | 2025-06-18 | mcp 1.9 | Claude Desktop |

Keep it in the README; update on every release; note the next protocol
revision you're validating against (2026-07-28 at authoring time).
