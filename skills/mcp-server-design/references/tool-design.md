# MCP tool-surface design — evidence and worked examples

Verified against primary sources 2026-07-20; spec revision 2025-11-25.
Portions synthesize concepts also taught by Anthropic's `mcp-builder` skill
(github.com/anthropics/skills, Apache-2.0) — rewritten and re-verified here.

**Contents:** [Evidence for the rules](#evidence-for-the-rules) ·
[Primitive decision tree](#primitive-decision-tree) ·
[Descriptions: bad → good](#descriptions-bad--good) ·
[Schemas: bad → good](#schemas-bad--good) ·
[Pagination & response contracts](#pagination--response-contracts) ·
[Annotations](#annotations) · [Error messages](#error-messages) ·
[Advanced patterns](#advanced-patterns) · [Sources](#sources)

## Evidence for the rules

- **Outcome tools beat endpoint wrappers** — universal consensus across
  Anthropic, Block, AWS, Workato and academic audits. MCP co-creator David Soria
  Parra on REST-to-MCP auto-converters: "it's a bit cringe" — they skip the
  domain judgment that makes a server usable.
- **Tool count degrades selection accuracy.** Loading a full GitHub server vs a
  focused set dropped selection accuracy ~24 points in one benchmark; a
  five-plus-ten-server telemetry study put weaker models below 90% accuracy at
  10–15 active tools. Treat every published cliff number as directional — the
  robust finding is the slope, not the threshold.
- **~350 tokens per tool definition**, injected every turn. 50 tools ≈ 17.5k
  tokens before the user types a word.
- **Descriptions are measurably bad in the wild**: an audit of 856 deployed
  tools across 103 servers found 56% fail to state their purpose clearly and 89%
  lack when-to-use guidance (arXiv:2602.14878).
- **Real consolidations**: GitHub Copilot 40→13 tools; Block rebuilt its Linear
  server three times, landing on 2 tools.

## Primitive decision tree

```
Does it change anything, or answer a query whose parameters
depend on the conversation?          → Tool (model-controlled)
Is it read-only reference data addressable by a URI,
useful as ambient context?           → Resource (application-controlled)
    …but must it work in every client?  → weakly-supported: consider a
                                          read-only tool instead, or both
Is it a repeatable multi-step procedure a HUMAN should
deliberately trigger?                → Prompt (user-controlled; slash command)
```

Client-support reality (verify against your target clients): tools are
universally supported; resources and prompts are not. A design that leans on
resources/prompts must name the clients it targets.

## Descriptions: bad → good

Bad (real production example):

```
Gets commits
```

Good:

```
Retrieves the most recent commits from a GitHub repository branch.
Use when the user asks about recent changes, commit history, or who
changed something. Not for diffs of a single commit (use
github_get_commit_diff) or for creating commits.
Args: owner (string, GitHub org/user), repo (string), branch (string,
default "main"), limit (integer 1-50, default 10).
Returns: JSON array sorted newest-first: sha, message, author, date.
```

Template — every tool description states:

1. What it does — one specific sentence, concrete output type.
2. When to use it — and when NOT to (name the sibling tool to use instead).
3. Each parameter's type, format, constraints, default.
4. Return shape, sort order, size limits.
5. Documented error strings the model may see.

Descriptions are prompts: refining them is a server-side deploy that improves
every connected agent without client changes. Iterate them from real transcripts
(see `mcp-server-testing`).

## Schemas: bad → good

Bad — the model must guess key names and value formats:

```json
{ "name": "search_orders",
  "inputSchema": { "type": "object",
    "properties": { "filters": { "type": "object" } } } }
```

Good — flat, typed, enumerated, defaulted:

```json
{ "name": "orders_search",
  "inputSchema": {
    "type": "object",
    "properties": {
      "email":  { "type": "string", "format": "email",
                  "description": "Customer email address" },
      "status": { "type": "string",
                  "enum": ["pending", "shipped", "delivered", "cancelled"],
                  "default": "pending" },
      "limit":  { "type": "integer", "minimum": 1, "maximum": 50,
                  "default": 20 },
      "cursor": { "type": "string",
                  "description": "Opaque pagination cursor from a previous call" },
      "response_format": { "type": "string",
                  "enum": ["concise", "detailed"], "default": "concise" }
    },
    "required": ["email"],
    "additionalProperties": false
  } }
```

Server naming (distinct from tool naming): generic, versionless —
`{service}_mcp` (Python) / `{service}-mcp-server` (Node); registry namespace
rules live in `mcp-server-deployment`.

Rules (spec 2025-11-25):

- `inputSchema` MUST be a valid JSON Schema object, never null; dialect defaults
  to **2020-12** when `$schema` is absent. No-parameter tools:
  `{"type": "object", "additionalProperties": false}`.
- Reject unknown fields (`additionalProperties: false` / Zod `.strict()` /
  Pydantic `extra="forbid"`) when you mean to be strict.
- Same concept ⇒ same name in every tool (`user_id` everywhere; never mix with
  `accountId`). Reconciliation costs tokens and breaks weaker models.
- Declare `outputSchema` where the return is structured; mechanics of
  `structuredContent` live in `mcp-server-implementation`.

## Pagination & response contracts

Every list-returning tool:

| Field | Direction | Contract |
| --- | --- | --- |
| `limit` | in | default 20–50, hard cap enforced server-side |
| `cursor` (or `offset`) | in | opaque cursor preferred; from prior response |
| `has_more` | out | boolean |
| `total_count` | out | integer when cheap to compute |
| `next_cursor` | out | present iff `has_more` |

Protocol list operations (`tools/list`, `resources/list`, `prompts/list`) use
cursor pagination natively (`params.cursor` → `nextCursor`).

Response shaping:

- `response_format: "concise" | "detailed"` — concise as default; Anthropic
  measured ~2/3 token reduction on its Slack server example.
- Return names alongside IDs (`"Jane Doe (usr_123)"`); models hallucinate less
  when follow-up parameters are human-readable.
- Truncate oversized payloads explicitly, stating how to fetch the remainder;
  a common client-side cap is ~25k tokens per tool response (Claude Code
  default — product fact, verify current value when load-bearing).

## Annotations

| Annotation | Meaning | Default |
| --- | --- | --- |
| `readOnlyHint` | no state modified | false |
| `destructiveHint` | may delete/irreversibly change data (only meaningful when not read-only) | true |
| `idempotentHint` | repeat call with same args = no additional effect | false |
| `openWorldHint` | touches external world beyond the backing system | true |

Plus `title` for display. Clients build confirmation UX from these; declare them
honestly. Clients MUST treat annotations from untrusted servers as untrusted —
they are hints, never a security mechanism (see `mcp-server-security`).

## Error messages

Errors are read by the model. Pattern: **state the problem + the recovery step**.

| Bad | Good |
| --- | --- |
| `Error 500` | `Search index temporarily unavailable. Retry in ~30s, or use orders_get(order_id) for a direct lookup.` |
| `Unauthorized` | `Token lacks scope "orders:read". Ask the user to re-authorize with that scope.` |
| `Invalid input` | `departure_date must be in the future (today is 2026-07-20). Format: YYYY-MM-DD.` |
| stack trace | never — leaks internals and burns context |

Since 2025-11-25 (SEP-1303), input-validation failures should be returned as
tool execution errors (`isError: true`) rather than protocol errors so the model
can read and self-correct. Wire mechanics: `mcp-server-implementation`.

## Advanced patterns

Use when the basic budget/consolidation rules aren't enough:

- **Toolsets / permission surfaces** — GitHub's official server groups tools
  into opt-in toolsets so clients load only what a session needs.
- **Progressive discovery** — a `tool_search` meta-tool (or client-side deferred
  loading) retrieves tool definitions on demand instead of loading all upfront;
  Anthropic shipped deferred-loading infrastructure supporting catalogs up to
  ~10k tools with top-5 retrieval.
- **HATEOAS navigator** — one `api_navigate(href, method, body)` tool over a
  hypermedia API whose `_links` gate valid next actions by resource state;
  collapses N tools to 1 and makes invalid transitions structurally impossible.
  Trade-off: pushes domain knowledge into API responses; hybrid (one navigator
  per bounded context + typed shortcuts for hot mutations) is safer.
- **Code execution with MCP** — the client writes code composing many tool
  calls in one shot (Anthropic engineering pattern); relevant when your server
  is one of dozens loaded, it rewards clean schemas and structured output.

## Sources

Primary, verified 2026-07-20:

- Tools spec + naming (SEP-986): <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>
- Prompts / resources spec: <https://modelcontextprotocol.io/specification/2025-11-25/server/prompts>, <https://modelcontextprotocol.io/specification/2025-11-25/server/resources>
- Changelog (2025-11-25 incl. SEP-1303, SEP-1613 JSON Schema 2020-12): <https://modelcontextprotocol.io/specification/2025-11-25/changelog>
- Anthropic engineering — writing effective tools, code execution with MCP: <https://www.anthropic.com/engineering>
- AWS Labs design guidelines: <https://github.com/awslabs/mcp/blob/main/DESIGN_GUIDELINES.md>
- Description-quality audit: <https://arxiv.org/abs/2602.14878>
- Practitioner syntheses (secondary; directional numbers): philschmid.de/mcp-best-practices, Block/GitHub engineering posts.
