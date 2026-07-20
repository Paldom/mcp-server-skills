# Setup prompt: build an MCP server end-to-end with these skills

Paste the block below into a Claude Code session (with this repo's skills
installed) to drive a full server build autonomously. Fill the two
`<placeholders>` first. It orchestrates the six skills in dependency order
with a verification gate after each phase. The prompt is ~3.4k chars —
within the 4,000-char `/goal` limit.

```text
/goal Build a production-quality MCP server for <SYSTEM: e.g. "our internal ticketing REST API">, target deployment <TARGET: "local stdio" or "remote Streamable HTTP">. Work autonomously through the phases below, in order; do not skip a gate. NEVER run git commit or git push - leave every change in the working tree for review.

Phase 1 - DESIGN (apply /mcp-server-design): decide build-vs-not, then produce DESIGN.md: outcome-oriented tool list (5-15 tools, snake_case service_action_resource names), primitive assignment (tool/resource/prompt with justification), per-tool description (what + when-to-use + not-for + params + returns), flat typed schemas with enums/defaults, pagination + response_format on list tools, error messages written as recovery instructions, honest annotations, destructive tools flagged for confirmation gates.
GATE 1: the design skill's lint_tool_surface.py exits 0 on the proposed surface (write tools.json from DESIGN.md).

Phase 2 - IMPLEMENT (apply /mcp-server-implementation): official SDK only (TypeScript ^1.29 + zod, or Python "mcp[cli]>=1.27,<2" FastMCP), shared API client + centralized error mapper first, then tools per DESIGN.md. Transport per <TARGET>: stdio (all logs to stderr) or Streamable HTTP (Origin validation -> 403, MCP-Protocol-Version handling, prefer stateless). Execution failures -> isError results with recovery text (Python: raise ToolError); structured output consistent with text blocks; progress + cancellation on any tool that can exceed ~30s; env config validated at startup. Tools whose modules are disjoint files MAY be implemented by parallel subagents AFTER the shared infra lands; everything else stays sequential.
GATE 2: build passes (tsc / py_compile), server starts, check_stdio_hygiene.py exits 0 (stdio targets), every tool + one error path each exercised in MCP Inspector.

Phase 3 - AUTH, only if <TARGET> is remote (apply /mcp-server-auth): OAuth 2.1 resource-server role against the org IdP - RFC 9728 protected resource metadata + WWW-Authenticate challenges, RFC 8707 audience validation (foreign tokens -> 401), scopes split read/write with step-up 403s, cached JWKS validation, no token passthrough. stdio target: env credentials only, skip this phase.
GATE 3: check_auth_endpoints.py exits 0 against the running server; a wrong-audience token is rejected in a live probe.

Phase 4 - SECURE (apply /mcp-server-security): walk the threat taxonomy and write dispositions in SECURITY-NOTES.md; guardrails in code (confirmation + idempotency keys on mutating tools, two-layer validation, path/SSRF guards where applicable); audit log per tool call to a separate store; per-tool rate limits + kill switch; external content fenced before returning.
GATE 4: security_checklist.py --repo . exits 0 and every TODO item has a written disposition.

Phase 5 - TEST (apply /mcp-server-testing): conformance suite green; ~10-question agent eval suite (read-only, verifiable, solved by you first, lint_eval_suite.py exits 0), run it, read failing transcripts, iterate tool descriptions once, re-run; record baseline accuracy vs a no-server run.
GATE 5: conformance passes; eval accuracy reported with held-out subset intact.

Phase 6 - SHIP PREP (apply /mcp-server-deployment): packaging for <TARGET> (npm/PyPI entrypoint or MCPB manifest with sensitive:true secrets; remote: health probes, per-tool logs/spans/metrics, canary plan), server.json for the MCP Registry validated by check_server_json.py, README compatibility note (protocol revisions, SDK versions, clients tested).
GATE 6: check_server_json.py exits 0; deployment docs name exact pinned install commands.

Definition of Done: all six gates passed with command output shown; DESIGN.md, SECURITY-NOTES.md, eval suite + accuracy report, and deployment artifacts exist; zero commits; final summary lists every file changed and every gate result.
```

## Notes

- Ordering matters: design feeds implementation; auth precedes the security
  review (the reviewer needs the real auth posture); testing precedes ship.
- Parallel subagents are safe only on disjoint file surfaces (per-tool
  modules in Phase 2); never parallelize across phases.
- Each gate is a deterministic script bundled with the corresponding skill —
  the agent must show the command output, not claim success.
- The skills pin spec revision 2025-11-25 and flag the 2026-07-28 revision's
  changes; re-run `/mcp-server-implementation`'s reference checks after major
  spec/SDK releases.
