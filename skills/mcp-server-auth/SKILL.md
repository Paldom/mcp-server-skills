---
name: mcp-server-auth
description: Implements MCP server authorization - OAuth 2.1 resource server role, RFC 9728/8414 discovery, PKCE, RFC 8707 audience validation, scopes, client registration. Use when adding auth, OAuth, tokens, or credentials to an MCP server, or debugging 401/403/discovery failures. Not for general threat hardening, transport wiring, or non-MCP app login.
---

# mcp-server-auth

Make an MCP server authenticate its callers correctly. The spec profiles OAuth
2.1 precisely; the documented failures this skill fixes are servers that invent
bearer-token schemes, pass client tokens through to downstream APIs, skip
discovery metadata (so no client can connect), or accept any validly-signed
token regardless of audience.

Targets spec revision **2025-11-25** (verified 2026-07-20):
<https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>.

## When NOT to use

- Threat modeling / injection / sandboxing → `mcp-server-security` (auth is one
  control; that skill owns the attack taxonomy).
- Transport mechanics (Origin validation, sessions, headers) →
  `mcp-server-implementation`. Hosting/gateways → `mcp-server-deployment`.
- OAuth for ordinary web/mobile apps — this is the MCP profile specifically.

## Workflow

### 1. Pick the auth model by transport

- **stdio (local subprocess)**: the OAuth spec does NOT apply — read
  credentials from the environment, scope the underlying API key minimally,
  never put secrets in client-config `args`.
- **Streamable HTTP**: authorization is OPTIONAL in the spec, and HTTP
  transports SHOULD conform to the OAuth 2.1 profile. Once you implement it,
  the MUSTs below are normative. Strong recommendation: any internet-exposed
  server implements it — scans keep finding thousands of open MCP endpoints.
  (Many secondary sources say "OAuth is mandatory for remote" — that is not
  what the spec says; don't repeat it.)
- A static shared API key is not a substitute for identity-scoped tokens: no
  per-user scoping, no revocation story, total blast radius. If a gateway
  terminates auth for you, the requirements below move there.

### 2. Be a resource server, not an authorization server

Your MCP server **validates** tokens; an AS (Auth0/Okta/Keycloak/Entra or your
IdP) issues them. Building your own AS is almost always the wrong call —
delegate. If the server must broker access to a third-party API, see step 6.

### 3. Publish discovery metadata (or no client can connect)

- **RFC 9728 Protected Resource Metadata** (MUST): serve
  `/.well-known/oauth-protected-resource` with your canonical `resource` URI
  and `authorization_servers`; AND/OR return
  `WWW-Authenticate: Bearer resource_metadata="<url>"` on 401 (clients try
  header first, then well-known — support both).
- The AS must offer RFC 8414 metadata or OIDC Discovery (2025-11-25 accepts
  either; clients must support both).
- Every 401/403 carries the right challenge — see the exact HTTP exchanges in
  `references/oauth-wire.md`.

### 4. Validate every token, every request

- `Authorization: Bearer <token>` on **every** request — sessions never carry
  auth (spec MUST NOT). Tokens never in query strings.
- **Audience validation (RFC 8707)**: accept only tokens whose audience is
  your canonical resource URI; a validly-signed, unexpired token for another
  resource → **401**. Clients send `resource=` on authorization and token
  requests; you enforce it on receipt.
- Validate locally: cache the AS JWKS and verify signature/exp/aud in-process
  (sub-ms) instead of a network introspection per call; re-fetch on key
  rotation.
- Insufficient scope at runtime → **403** with `error="insufficient_scope"` +
  the required `scope` in `WWW-Authenticate` (SEP-835) so clients can step up
  incrementally. Publish minimal scopes; separate read from write.
- PKCE: clients MUST use S256 and MUST refuse an AS whose metadata lacks
  `code_challenge_methods_supported` — when you operate the AS config, make
  sure that field is present or every spec-conforming client will refuse you.

### 5. Client registration: CIMD first

Priority order (2025-11-25): pre-registered credentials → **Client ID Metadata
Documents** (the client_id is an HTTPS URL serving the client's metadata;
recommended when the AS advertises `client_id_metadata_document_supported`) →
RFC 7591 Dynamic Client Registration only as back-compat fallback (deprecated
in the next revision) → prompt the user. If you allow DCR: allowlist/exact
redirect URIs, no wildcards — open DCR + arbitrary redirect URI is a
disclosed one-click account-takeover class.

### 6. Never pass tokens through; proxy with consent

- **Token passthrough is forbidden**: never accept a token not issued for your
  server, never forward the client's token upstream. Downstream APIs are
  called with credentials the *server* owns (or an explicit token exchange).
- If your server fronts a third-party AS with a static client_id (the
  "OAuth proxy" shape): obtain **per-client consent** before every forward,
  exact-match redirect URIs, bind and verify `state` — the confused-deputy
  writeups that broke real products in 2025 all violated one of these.

### 7. Verify the flow end to end

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check_auth_endpoints.py" https://your-host/mcp
```

probes: unauthenticated request → 401 + parseable challenge; PRM well-known
resolves and matches the server URL; AS metadata reachable with S256
advertised. Then run a real client (MCP Inspector supports the OAuth flow) and
confirm a wrong-audience token is rejected. Conformance suite:
`npx @modelcontextprotocol/conformance server --url ...`.

## Output spec

A server that: serves RFC 9728 PRM (+ challenge headers), validates
signature/expiry/**audience** on every request via cached JWKS, returns the
401/403 contract with correct `WWW-Authenticate`, scopes split read/write with
step-up, registers clients via CIMD (DCR only as fallback, allowlisted),
touches downstream APIs only with its own credentials, and passes the probe
script + a live client flow.

## Gotchas

- **Sessions are not auth** — an `Mcp-Session-Id` proves nothing; validate the
  bearer token on every request even mid-session.
- **SSRF in discovery**: SDK clients have fetched attacker-controlled
  `resource_metadata` URLs before validating them (disclosed against both
  major SDKs) — if you implement client-side discovery anywhere, validate
  scheme/host before fetching; as a server, never reflect user input into
  challenge URLs. Full taxonomy: `mcp-server-security`.
- **Issuer validation**: verify AS metadata `issuer` matches where you fetched
  it (RFC 8414 §3.3); mixed-endpoint metadata (legit authorization_endpoint,
  attacker token_endpoint) is a disclosed credential-theft class. The
  2026-07-28 revision adds RFC 9207 `iss` checks and requires client
  credentials keyed per-issuer — align now.
- Access tokens short-lived (minutes-hours); refresh handled by the client and
  AS, not you. Log auth failures with reasons; never log tokens.
- The auth extension ecosystem (`modelcontextprotocol/ext-auth`) hosts
  optional additions — check it before inventing an extension.

## Pointers

- `references/oauth-wire.md` — the exact HTTP exchanges (401/403 challenges,
  PRM and AS metadata JSON, CIMD document, token validation pseudocode, RFC
  map, IdP wiring notes).
- `scripts/check_auth_endpoints.py` — deterministic discovery/challenge probe
  (stdlib-only; non-zero exit on failures).
