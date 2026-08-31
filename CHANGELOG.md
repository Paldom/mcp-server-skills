# Changelog

All notable changes to this repository's skills are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [SemVer](https://semver.org) on the plugin manifest
(breaking skill-interface change → major, new skill → minor, fix → patch).

## [Unreleased]

## [0.2.0] - 2026-08-31

### Added
- Adopted the current skillskit gate: executed trigger evals scoring every trigger
  prompt against every skill description (rank-1 routing accuracy 82.0%), a security
  scan over skill content and bundled scripts, ruff lint and format, README-shape
  validation, pre-commit hooks and a write-time lint hook.

### Changed
- Skill descriptions sharpened where the eval gate showed a sibling outranking a
  skill on its own trigger prompts, or a stated non-trigger matching better than any
  trigger. Fixes changed the scope boundary, not just the wording.

### Fixed
- Findings the new lint gate surfaced in this repo's own scripts, fixed at the
  source; where a rule was wrong for a line it is suppressed there with its reason.


### Added
- `mcp-server-design`: designs an MCP server's tool/resource/prompt surface — outcome-oriented consolidation, tool budget, SEP-986 naming, descriptions-as-prompts, flat typed schemas, pagination contracts, agent-readable errors; ships a deterministic surface linter.
- `mcp-server-implementation`: implements MCP servers on the official TS/Python SDKs — current registration APIs, both transports (stdio hygiene, Streamable HTTP wire contract), isError vs protocol errors, structured output, progress/cancellation; ships a stdio-hygiene checker and per-language reference implementations.
- `mcp-server-auth`: implements MCP authorization as an OAuth 2.1 resource server — RFC 9728/8414 discovery, PKCE, RFC 8707 audience validation, scope step-up, CIMD-first client registration, no-token-passthrough and confused-deputy rules; ships a discovery-endpoint probe.
- `mcp-server-security`: hardens MCP servers against the documented attack taxonomy (tool poisoning, rug pulls, injection via tool results, session hijacking, SSRF, command injection, supply chain, denial of wallet) with guardrails-in-code, idempotency, audit stores, sandboxing, kill switches; ships a deterministic CI checklist runner.
- `mcp-server-testing`: tests and evaluates MCP servers — Inspector protocol passes, the official conformance suite, ~10-question verifiable agent evals with transcript-driven description iteration, tool-selection classification evals, CI regression gates, load-test patterns; ships an eval-suite linter.
- `mcp-server-deployment`: deploys, operates, and distributes MCP servers — stateless scaling with session externalization, per-tool observability, health probes, canary rollouts, MCPB bundles, MCP Registry publishing, semver + protocol compatibility practice; ships a server.json gate.
- Repository scaffolded from the skills template.
