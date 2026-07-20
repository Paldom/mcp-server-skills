# Agent evaluations for MCP servers

Methodology synthesized from Anthropic's `mcp-builder` skill
(github.com/anthropics/skills, Apache-2.0 — rewritten here), Anthropic
engineering guidance, and GitHub's offline-eval practice; verified 2026-07-20.

**Contents:** [Question requirements](#question-requirements) ·
[Good vs bad questions](#good-vs-bad-questions) ·
[Creation process](#creation-process) · [Suite format](#suite-format) ·
[Harness design](#harness-design) · [Report-driven iteration](#report-driven-iteration) ·
[Selection evals](#selection-evals) · [Load-test template](#load-test-template) ·
[CLI reference](#cli-reference)

## Question requirements

Each of the ~10 questions must be:

| Property | Meaning |
| --- | --- |
| Independent | no ordering or shared state between questions |
| Read-only | no writes/mutations; destructive paths are tested as guardrail regressions, not evals |
| Realistic | a task a human user actually brings to this system |
| Complex | multi-hop: each step consumes the previous step's findings; may take dozens of tool calls, paging, old data |
| Un-shortcuttable | paraphrase the target content — a single keyword search must not solve it |
| Stable | answer based on closed/historical facts; fixed date windows; never live counts or "latest" |
| Verifiable | ONE answer checkable by string comparison, format declared in the question ("YYYY-MM-DD", "True or False") |
| Human-readable | prefer names/dates over opaque IDs; vary answer modalities across the suite |

Deliberate tool-choice ambiguity is good (hard decisions are signal); an
unsolvable question or two is acceptable diagnostic; a wrong reference answer
is poison — verify every answer by solving it with the tools yourself first.

## Good vs bad questions

Bad (keyword-shortcuttable, unstable, unverifiable):

> "How many open tickets are there?" (live count — unstable)
> "Find the ticket about login errors." (single keyword search; answer is a list)

Good (multi-hop, stable, single verifiable answer):

> "The incident retro that mentioned a database migration rollback in Q3 2025
> names an on-call engineer. In which month did that engineer author their
> first runbook page? Answer format: YYYY-MM."

## Creation process

1. Study the underlying system's docs (parallelize with subagents if large).
2. Inspect the server's tool list — **without calling the tools yet** and
   without reading the server's source (the eval must reflect the interface,
   not the implementation).
3. Explore read-only with small limits (`limit<10`, pagination) to find rich
   content areas — protect your context; subagents help here too.
4. Draft ~10 questions per the table; declare each answer format.
5. Solve every question with the tools; correct or delete; keep 2-3 held out
   from any description-tuning loop.

## Suite format

XML (compatible with Anthropic's published harness) or JSON:

```xml
<evaluation>
  <qa_pair>
    <question>...multi-hop question... Answer format: YYYY-MM-DD.</question>
    <answer>2025-09-14</answer>
  </qa_pair>
</evaluation>
```

Lint before running: `python3 "${CLAUDE_SKILL_DIR}/scripts/lint_eval_suite.py" evals.xml`.

## Harness design

Agent loop per question: system prompt forces a structured reply
(`<summary>` of steps, `<feedback>` on tool friction, `<response>` = bare
answer, with a NOT_FOUND fallback); the harness connects over
stdio/Streamable HTTP, exposes the server's tools, iterates until the model
answers, then scores `response` by normalized exact match. Collect per
question: correct/incorrect, wall time, tool-call count and sequence, tokens,
and the agent's `feedback` text (it names confusing tools remarkably well).
Anthropic ships a runnable reference harness in its `mcp-builder` skill
(`scripts/evaluation.py`, Apache-2.0) — usable as-is or as a template; grade
with a current model, and prefer a different model/session than the one under
tuning (self-grading is near random).

## Report-driven iteration

| Symptom in report | Usual fix |
| --- | --- |
| low accuracy, few tool calls | descriptions don't announce capability — rewrite when-to-use |
| low accuracy, many wandering calls | overlapping tools / vague schemas — disambiguate, add "Not for" |
| timeouts, huge payloads | missing pagination/response_format caps |
| wrong-parameter errors | schema too loose — enums, formats, examples |
| agent feedback names a tool | believe it — that description is the bug |

Change descriptions/schemas (rules in `mcp-server-design`), re-run, compare
against the held-out subset to catch overfitting. Stop when held-out accuracy
plateaus — then a no-server baseline run tells you the server's net value.

## Selection evals

Offline, no execution — treat tool choice as classification:

```json
[{ "prompt": "what changed in the last deploy of api-gateway?",
   "expected_tool": "deploys_get_latest" },
 { "prompt": "who owns the payments service?",
   "expected_tool": "services_get_owner" }]
```

Run the prompts against the model with only the tool catalog loaded; score
top-1 selection. Fix failures by rewriting the colliding descriptions, never
by editing eval prompts. Wire into CI with a threshold; description-overlap
detectors catch collisions before they ship.

## Load-test template

k6, realistic `tools/call` traffic:

```javascript
import http from "k6/http";
import { check } from "k6";
export const options = {
  vus: 100, duration: "5m",
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<500"] },
};
export default function () {
  const res = http.post("https://mcp.example.com/mcp", JSON.stringify({
    jsonrpc: "2.0", id: 1, method: "tools/call",
    params: { name: "orders_search", arguments: { email: "load@example.com" } },
  }), { headers: { "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "Authorization": `Bearer ${__ENV.TOKEN}` } });
  check(res, { ok: (r) => r.status === 200 || r.status === 202 });
}
```

Include one expensive tool in the mix; identify the limiting resource
(downstream API, DB pool, CPU) in the report, not just pass/fail.

## CLI reference

```bash
npx @modelcontextprotocol/inspector <server-launch-cmd>   # web UI :6274; -e KEY=val for env
uv run mcp dev server.py                                  # python dev shortcut
npx @modelcontextprotocol/conformance server --url http://localhost:3000/mcp
npx @modelcontextprotocol/conformance client --command "node dist/index.js" --scenario initialize
npx @modelcontextprotocol/conformance list                # scenarios; --spec-version selects revision
```
