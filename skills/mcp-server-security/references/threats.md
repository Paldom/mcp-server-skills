# MCP threat taxonomy — mechanisms, incidents, defenses

Compiled from primary disclosures, the normative spec security pages, and
institutional guidance; verified 2026-07-20. Normative source:
<https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices>.

**Contents:** [Tool poisoning](#tool-poisoning) · [Rug pulls](#rug-pulls) ·
[Injection via tool results](#prompt-injection-via-tool-results) ·
[Confused deputy](#confused-deputy) · [Session hijacking](#session-hijacking) ·
[SSRF](#ssrf) · [Command injection & local servers](#command-injection--local-servers) ·
[Supply chain](#supply-chain) · [Denial of wallet](#denial-of-wallet) ·
[Institutional guidance](#institutional-guidance-index)

## Tool poisoning

**Mechanism.** Tool descriptions, schema field docs, and other server metadata
enter the model's context verbatim. A hostile server hides instructions there —
visible to the model, invisible in most client UIs. Payloads hide in any schema
field, zero-width Unicode, or Base64 (Invariant Labs' original disclosure).

**Defenses.** For server authors: keep descriptions boring, instructional-free,
reviewed like code. For consumers: pin server versions, hash tool descriptions
and alert on change, scan catalogs in CI (`mcp-scan`-class tools), prefer
clients that display full descriptions at approval time.

## Rug pulls

**Mechanism.** A server passes review with benign tools, then swaps
descriptions/behavior later — via `notifications/tools/list_changed` or a
package update. Clients generally do NOT re-prompt when descriptions change.
**Incident:** `postmark-mcp` (npm) shipped 15 clean releases, then v1.0.16
silently BCC'd every email through the attacker's address.

**Defenses.** Version-pin server packages (no `@latest` in client configs);
content-hash tool descriptions at install and diff on every session start;
alert on drift; registries and marketplaces do not vet updates for you.

## Prompt injection via tool results

**Mechanism.** A tool returns external content (web page, email, document,
ticket text) containing instructions; the model obeys them. This composes with
private data + any exfiltration channel into Simon Willison's "lethal
trifecta". Research finding worth internalizing: **more capable,
better-instruction-following models are MORE susceptible**, not less.

**Defenses (server side).** Wrap all external content in explicit delimiters
(`<external_data source="crm-ticket">…</external_data>`); screen for injection
phrasing before returning; strip active content (HTML/JS); cap sizes. Apply
unconditionally — provenance, not content, decides what gets fenced. Neither
fencing nor screening alone is sufficient; use both, and say in tool docs that
output is untrusted data.

## Confused deputy

**Mechanism.** The server holds a powerful credential (its own API key, or a
static OAuth client_id at a third-party AS) and exercises it on behalf of the
wrong caller. The 2025 one-click account-takeover disclosures (Obsidian
Security and others) chained: MCP server acting as both AS and OAuth client +
shared static client_id + open dynamic registration + wildcard redirect URIs +
missing per-client consent.

**Defenses.** Per-client consent before any third-party forward; exact
redirect-URI matching; `state` bound to session; audience validation and the
token-passthrough ban (mechanics: `mcp-server-auth`); execute tools in the
**requesting user's** permission context — one shared service account
collapses tenancy.

## Session hijacking

**Mechanism.** Predictable or long-lived `Mcp-Session-Id` values reused as de
facto authentication let an attacker resume or inject into someone else's
session.

**Defenses (spec MUSTs).** Sessions are never authentication — verify the
bearer token on every request; IDs from a secure RNG, non-deterministic; bind
IDs to user identity (`user_id:session_id` keys) so a guessed ID is useless
across principals; rotate/expire; invalid session → 404 and re-initialize.

## SSRF

**Mechanism.** Any tool that fetches URLs — or the OAuth discovery flow
itself — can be pointed at internal targets (`169.254.169.254` cloud metadata,
internal admin panels). Disclosed against both major SDKs: clients fetched
`WWW-Authenticate: resource_metadata` URLs before validating origin, making a
zero-interaction blind SSRF proxy (validation ran after the request).

**Defenses.** Validate scheme/host/port BEFORE fetching; block private,
loopback, and link-local ranges (resolve first — DNS can point anywhere);
HTTPS-only for discovery; egress proxy with an allowlist for fetch-class
tools; cap sizes and follow-redirect counts.

## Command injection & local servers

**Mechanism.** Tool args interpolated into shells, and the stdio launch model
itself: client configs execute a command line with parameters. The official
SDKs pass stdio params to the host without sanitization — Anthropic's
documented position is that this is by-design (a local MCP server IS code
execution); mitigations belong to implementers and hosts. Related CVEs hit
downstream products (LiteLLM, Cursor, LibreChat, older MCP Inspector —
CVE-2025-49596; `mcp-remote` — CVE-2025-6514, CVSS 9.6).

**Defenses.** Never shell out with user-influenced strings — use exec-array
APIs and safe libraries; treat every local server install as granting code
execution: review, pin, sandbox (container/micro-VM, non-root, read-only FS,
minimal egress); filesystem tools enforce a resolved-path allowlist
(`path.resolve` + prefix check, both symlink-aware).

## Supply chain

**Mechanism.** Servers are npm/PyPI packages with the usual ecosystem risks,
plus registries that do not security-review listings, plus configs that run
`npx -y package@latest` (auto-updating attacker channel).

**Defenses.** Pin exact versions + lockfiles in server repos AND client
configs; review before install; SBOM + dependency scanning; prefer packages
with provenance/signing; mirror internally for fleet deployments.

## Denial of wallet

**Mechanism.** Agents loop; tools cost money (LLM calls, paid APIs, egress).
Unbounded consumption is OWASP LLM Top-10 #10; documented LLM-key abuse runs
to tens of thousands of dollars per day.

**Defenses.** Per-identity and per-tool quotas; cost budgets with hard stops;
`retry-after` on limit responses (agents honor it); alert on per-caller cost
anomalies; kill switches per tool.

## Institutional guidance index

| Source | What it gives you |
| --- | --- |
| Spec security best practices (normative): <https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices> | the MUSTs: confused deputy, token passthrough, session rules, local-compromise, URL validation |
| NSA Cybersecurity Information Sheet on MCP (2026): nsa.gov | enterprise framing; MCP leaves auth/expiry/audit to implementers |
| OWASP GenAI — Practical Guide for Secure MCP Server Development: genai.owasp.org | 8-domain checklist incl. token passthrough elimination, signed manifests |
| CSA — Agentic MCP Security Best Practices: cloudsecurityalliance.org | threat categories + maturity model for programs |
| AWS Labs `DESIGN_GUIDELINES.md`: github.com/awslabs/mcp | bounded-context and schema discipline from a large server fleet |
| OWASP LLM Top 10: genai.owasp.org | injection + unbounded-consumption framing auditors recognize |

Cite these to auditors; cite the disclosures above to engineers.
