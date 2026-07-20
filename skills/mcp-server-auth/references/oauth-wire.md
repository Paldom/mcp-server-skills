# MCP authorization — the wire contract

Verified against spec revision 2025-11-25 on 2026-07-20
(<https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>).

**Contents:** [RFC map](#rfc-map) · [The 401/403 contract](#the-401403-contract) ·
[Protected resource metadata](#protected-resource-metadata) ·
[AS metadata](#as-metadata) · [Token validation](#token-validation) ·
[Client ID Metadata Documents](#client-id-metadata-documents) ·
[IdP wiring notes](#idp-wiring-notes) · [Flow summary](#flow-summary)

## RFC map

| Standard | Role in MCP |
| --- | --- |
| OAuth 2.1 (draft-13) | base framework; PKCE required; implicit + password grants gone |
| RFC 9728 | Protected Resource Metadata — how clients find your AS (server MUST implement) |
| RFC 8414 / OIDC Discovery | AS metadata — clients MUST support both |
| RFC 8707 | Resource Indicators — audience-restricts tokens to your server (clients MUST send; you MUST enforce) |
| CIMD (draft-ietf-oauth-client-id-metadata-document) | recommended client registration (client_id = HTTPS URL) |
| RFC 7591 | Dynamic Client Registration — back-compat fallback; deprecated in the 2026-07-28 revision |
| RFC 9207 (`iss` in authorization response) | added by the 2026-07-28 revision; validate when present |

## The 401/403 contract

No/invalid/expired/wrong-audience token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"
```

Valid token, missing scope (step-up, SEP-835):

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders:write",
  resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"
```

Challenge scopes are authoritative — clients re-authorize with exactly what you
name (retry-limited). Clients discover via the header first, then fall back to
the well-known path (SEP-985) — implement both.

## Protected resource metadata

`GET https://mcp.example.com/.well-known/oauth-protected-resource`
(path-suffixed variant for servers below a path: `/.well-known/oauth-protected-resource/mcp`):

```json
{
  "resource": "https://mcp.example.com/mcp",
  "authorization_servers": ["https://auth.example.com"],
  "scopes_supported": ["orders:read", "orders:write"],
  "bearer_methods_supported": ["header"]
}
```

`resource` is your **canonical URI** — the same value clients put in RFC 8707
`resource=` parameters and the audience you enforce. Keep it exact (scheme,
host, port, path).

## AS metadata

Your AS must serve RFC 8414 (`/.well-known/oauth-authorization-server`) or
OIDC discovery (`/.well-known/openid-configuration`); clients try both in a
defined order (path-insertion before path-appending for path-ful issuers).
Non-negotiable fields for MCP clients:

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/authorize",
  "token_endpoint": "https://auth.example.com/oauth/token",
  "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
  "code_challenge_methods_supported": ["S256"],
  "client_id_metadata_document_supported": true
}
```

Clients MUST refuse an AS whose metadata omits
`code_challenge_methods_supported` — a missing field bricks spec-conforming
clients even if PKCE actually works. Validate `issuer` equals the metadata's
own origin (RFC 8414 §3.3); mixed-endpoint metadata is a disclosed
credential-theft vector.

## Token validation

Per request (pseudocode):

```
token = bearer_from_authorization_header(request)   # 401 if absent/malformed
claims = jwt_verify(token, jwks_cache)              # sig + exp + iat; 401 on failure
if canonical_resource_uri not in claims.aud: 401    # RFC 8707 audience — the MCP-specific check
if required_scope(tool) not in claims.scope: 403 insufficient_scope
request.identity = claims.sub                       # drives tenancy, audit, rate limits
```

- JWKS cached with sensible TTL + kid-based refresh; no per-request network.
- Opaque tokens → RFC 7662 introspection (cache decisions briefly).
- Reject `none` alg, enforce expected `iss`, cap clock skew.
- Never accept a token "because it's from our IdP" — audience is the check
  that defeats replay of tokens minted for other services (confused deputy).
- Derive the downstream tenant/DB handle from the validated identity
  per-request; a single shared service account collapses your tenancy.

## Client ID Metadata Documents

The client's `client_id` IS an HTTPS URL serving its metadata:

```json
{
  "client_id": "https://client.example.com/.well-known/oauth-client",
  "client_name": "Example MCP Client",
  "redirect_uris": ["https://client.example.com/callback"],
  "token_endpoint_auth_method": "none",
  "grant_types": ["authorization_code"],
  "response_types": ["code"]
}
```

The AS fetches it (SSRF-guard that fetch), caches it, and shows `client_name` +
origin on consent. Advantages over DCR: no open registration endpoint, stable
identity, revocable by the client at its own URL. Keep DCR (RFC 7591) only for
legacy clients, with allowlisted exact redirect URIs.

## IdP wiring notes

- **Auth0/Okta/Entra/Keycloak**: create an API/resource entity whose
  identifier equals your canonical resource URI so `aud` comes out right;
  enable the authorization-code + PKCE grant for MCP clients; define
  read/write scopes; Entra lacks CIMD/DCR in places — pre-registered clients
  are the fallback (the spec's registration priority list exists for exactly
  this).
- Multi-tenant: one PRM per logical server URL; audience per tenant only if
  the URLs differ.
- The upcoming revision requires clients to key stored credentials by issuer
  and re-register when the AS changes — don't share client credentials across
  authorization servers.

## Flow summary

```
Client → MCP server:  POST /mcp (no token)
MCP server → Client:  401 + WWW-Authenticate(resource_metadata)
Client:               GET PRM → GET AS metadata (8414/OIDC)
Client → AS:          authorize (PKCE S256, resource=<canonical URI>, scopes)
AS → Client:          code → token (aud = canonical URI)
Client → MCP server:  POST /mcp, Authorization: Bearer <token>   [every request]
MCP server:           verify sig/exp/aud/scope → serve; 403 challenge to step up
```
