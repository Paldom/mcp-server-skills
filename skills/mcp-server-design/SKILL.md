---
name: mcp-server-design
description: Designs an MCP server's tool/resource/prompt surface - outcome-oriented consolidation, tool budget, naming, descriptions-as-prompts, flat typed schemas, pagination, agent-readable errors. Use when planning what an MCP server should expose, fixing wrong-tool choices by improving names and descriptions, or turning an API into MCP tools. Not for writing server code, OAuth, or deployment.
---

# mcp-server-design

Design the surface an MCP (Model Context Protocol) server exposes to AI agents —
which tools/resources/prompts exist, what they're named, what their schemas and
descriptions say. This is the highest-leverage phase: most bad MCP servers fail
here, not in code. The failure this skill fixes: 1:1 API-wrapped, over-tooled,
under-described servers that tank agent tool-selection accuracy and burn context.

Facts below target MCP spec revision **2025-11-25** (current as of 2026-07-20).

## When NOT to use

- Writing the server code with an SDK → `mcp-server-implementation`.
- Adding OAuth/tokens → `mcp-server-auth`. Threat modeling → `mcp-server-security`.
- Testing/evals → `mcp-server-testing`. Shipping/registry → `mcp-server-deployment`.
- Designing plain REST/GraphQL APIs for human developers — different consumer,
  different rules (verbose CRUD is fine there; it is the anti-pattern here).
- Choosing which existing MCP servers to install (consumer question, not design).

## Workflow

### 1. Decide whether a server should exist

Build an MCP server when **2+ AI clients** need autonomous access to the system,
or a workflow is reused across sessions ("earns its keep on the third reuse").
One bespoke agent you fully control + a one-off task → direct tool/function
integration is simpler. A single static value → a resource on an existing server,
not a new one. Check <https://github.com/modelcontextprotocol/servers> and the
MCP Registry first — don't rebuild what exists.

### 2. Derive tools from workflows, not endpoints

Work **top-down from the user workflows** the agent must complete; never
bottom-up from the API surface. Each tool should complete an outcome, doing
multi-step orchestration server-side:

- `get_user` + `list_orders` + `get_status` → **one** `orders_track_latest(email)`
- `list_users` + `list_events` + `create_event` → `calendar_schedule_event(...)`
- `read_logs` (dump) → `logs_search(query)` returning matched lines + context

1:1 REST/OpenAPI auto-wrapping is the most-documented MCP anti-pattern: it
multiplies round-trips, tokens, and hallucinated parameters. If a workflow needs
~5 chained tool calls, collapse it into one tool.

### 3. Enforce a tool budget

Tool definitions are injected into the model's context every turn (~350
tokens/tool) and selection accuracy degrades as the catalog grows — production
teams converge on **5–15 tools per server** (heuristic, not spec law; weaker
models degrade earlier). Real fixes went 40→13 tools (GitHub Copilot) and 3
rebuilds→2 tools (Block's Linear server). Need more? Split by **domain**,
**permission level** (read vs write), or **performance profile** — never by API
resource. Run `scripts/lint_tool_surface.py` (below) to gate the count and names.

### 4. Assign each capability to the right primitive

Control-model test — *who decides when it happens?*

| Primitive | Controlled by | Use for | Notes |
| --- | --- | --- | --- |
| **Tool** | model | actions, side effects, dynamic queries | the default; validated input |
| **Resource** | application | read-only reference data at a URI (`db://schema`) | least-supported primitive across clients — verify your target clients before relying on it |
| **Prompt** | user | deliberate multi-step workflow templates ("SOPs") | surfaces as slash commands |

Don't cram workflow instructions into tool descriptions when a prompt is the
right home, and don't model pure reference data as a parameterless tool without
considering a resource first.

### 5. Name tools per current spec guidance

`{service}_{action}_{resource}` in `snake_case`: `slack_send_message`,
`tickets_search`, `sentry_get_error_details`. Spec (SEP-986, 2025-11-25): 1–128
chars, case-sensitive, only `A-Za-z0-9_-.`, unique per server. The service
prefix prevents collisions when several servers are active. Verb-first actions;
no spaces/brackets (some clients won't surface the tool at all).

### 6. Write descriptions as prompts, schemas as contracts

The description is what the model routes on — write it like onboarding docs for
a new hire, not API docs. State: what it does (one specific sentence), when to
use / when NOT to use, each parameter's exact format, and the return shape.
"Gets commits" is a real production description and it is useless.

Schemas are validated contracts, not hints: **flat, typed, top-level parameters**
with enums for constrained values, defaults, and unambiguous names (`user_id`,
never `user` or a nested `filters: dict` the model must guess). Constraints
belong in the schema (the protocol validates them), not in prose. Keep
terminology identical across tools (`user_id` everywhere — never `user_id` here
and `accountId` there).

### 7. Design responses for a context window

- **Paginate every list**: `limit` (default 20–50, capped), cursor/offset in,
  `has_more` + `total_count` out. Never dump unbounded records.
- **`response_format` parameter** (`"concise"` default / `"detailed"`): concise
  responses cut tokens ~2/3 in Anthropic's Slack example.
- Prefer **human-readable identifiers** (names alongside IDs) — resolving opaque
  UUIDs to names measurably reduces hallucinated follow-up parameters.
- Cap response size (~25k tokens is a common client-side cap) and tell the agent
  how to get the rest (offset/filter), don't truncate silently.

### 8. Write errors as recovery instructions

Tool errors are read by the model, not the user. Every failure message should
say what went wrong and what to do next:

> "Project 'proj_abc123' not found. Call `projects_list` to see valid IDs."
> "Rate limited. Retry after 30 seconds."

not `Error 500` / raw tracebacks. (Wire-level mechanics — `isError` vs protocol
errors — live in `mcp-server-implementation`.)

### 9. Declare honest annotations and gate destructive tools

Annotate behavior: `readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint` (+ `title`). Clients drive confirmation UX from these — a lying
annotation is a security bug. Make reads easy and writes expensive: destructive
tools get explicit confirmation flows. (Full threat model: `mcp-server-security`.)

### 10. Lint the surface

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/lint_tool_surface.py" tools.json
```

Checks names (spec regex + snake_case + shared prefix), tool count, description
quality floors, schema flatness/enums. Non-zero exit = fix before implementing.

## Output spec

A design document (or direct edits) containing: the build/no-build decision with
reasoning; a tool table (name, one-line outcome, annotations); primitive
assignments with justification; per-tool description + flat typed schema +
pagination/response_format for list tools; error-message examples; open
questions for evaluation. Hand off to `mcp-server-implementation` to code it.

## Gotchas

- **Tool budget numbers are heuristics**, not spec — the direction (fewer,
  higher-signal tools) is strongly corroborated; exact cliffs vary by model.
- "GET→resource, POST→tool" is wrong often enough to mislead — ask "is the model
  fetching context, or doing work?" instead.
- Resources/prompts have **uneven client support**; a design that depends on
  them must name its target clients or fall back to tools.
- Don't design around a single model: schemas that only a frontier model can
  navigate fail on the weakest client that connects.
- A 2026-07-28 spec revision (release candidate at authoring time) reshapes
  transports/lifecycle but does **not** change these surface-design rules;
  verify naming guidance at <https://modelcontextprotocol.io/specification> if
  months have passed.

## Pointers

- `references/tool-design.md` — worked examples (bad→good descriptions and
  schemas), the annotations table, pagination/response contracts, token-cost
  numbers with sources, primitive decision tree, advanced patterns (HATEOAS
  navigator, progressive tool discovery).
- `scripts/lint_tool_surface.py` — deterministic surface gate (stdlib-only).
