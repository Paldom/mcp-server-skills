# Changelog

All notable changes to this repository's skills are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org) on the plugin manifest
(breaking skill-interface change → major, new skill → minor, fix → patch).

## [Unreleased]

### Added
- `mcp-server-design`: designs an MCP server's tool/resource/prompt surface — outcome-oriented consolidation, tool budget, SEP-986 naming, descriptions-as-prompts, flat typed schemas, pagination contracts, agent-readable errors; ships a deterministic surface linter.
- `mcp-server-implementation`: implements MCP servers on the official TS/Python SDKs — current registration APIs, both transports (stdio hygiene, Streamable HTTP wire contract), isError vs protocol errors, structured output, progress/cancellation; ships a stdio-hygiene checker and per-language reference implementations.
- `mcp-server-auth`: implements MCP authorization as an OAuth 2.1 resource server — RFC 9728/8414 discovery, PKCE, RFC 8707 audience validation, scope step-up, CIMD-first client registration, no-token-passthrough and confused-deputy rules; ships a discovery-endpoint probe.
- `mcp-server-security`: hardens MCP servers against the documented attack taxonomy (tool poisoning, rug pulls, injection via tool results, session hijacking, SSRF, command injection, supply chain, denial of wallet) with guardrails-in-code, idempotency, audit stores, sandboxing, kill switches; ships a deterministic CI checklist runner.
- `mcp-server-testing`: tests and evaluates MCP servers — Inspector protocol passes, the official conformance suite, ~10-question verifiable agent evals with transcript-driven description iteration, tool-selection classification evals, CI regression gates, load-test patterns; ships an eval-suite linter.
- `mcp-server-deployment`: deploys, operates, and distributes MCP servers — stateless scaling with session externalization, per-tool observability, health probes, canary rollouts, MCPB bundles, MCP Registry publishing, semver + protocol compatibility practice; ships a server.json gate.
- Repository scaffolded from the skills template.
