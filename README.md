# Mcp Server Skills

[![CI](https://github.com/Paldom/mcp-server-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/Paldom/mcp-server-skills/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![skills.sh](https://skills.sh/b/Paldom/mcp-server-skills)](https://skills.sh/Paldom/mcp-server-skills)

Agent Skills for designing and implementing Model Context Protocol (MCP) servers - server architecture, tools, resources, prompts, transports, authorization, testing, and deployment.

Agent Skills for [Claude Code](https://code.claude.com/docs/en/skills) (and any
[Agent Skills](https://agentskills.io)-compatible tool). Each skill is a folder under
[`skills/`](skills/) with a single-purpose `SKILL.md`, trigger evals, and optional
scripts/references — validated on every write, commit, and PR.

## Quick start

Install with the [skills CLI](https://skills.sh) — auto-detects 70+ agents
(Claude Code, Codex, Cursor, Copilot, pi, …):

```bash
npx skills add Paldom/mcp-server-skills                  # all detected agents
npx skills add Paldom/mcp-server-skills -a codex -a pi   # or target specific agents
```

Or with the [GitHub CLI](https://cli.github.com/manual/gh_skill_install) (≥ 2.90),
including version-pinned installs from releases:

```bash
gh skill install Paldom/mcp-server-skills
gh skill install Paldom/mcp-server-skills <skill> --pin <tag>
```

Or as a Claude Code plugin:

```
/plugin marketplace add Paldom/mcp-server-skills
/plugin install mcp-server-skills@mcp-server-skills
```

Or copy a single skill into a project:

```bash
git clone https://github.com/Paldom/mcp-server-skills.git
cp -r mcp-server-skills/skills/<skill-name> your-project/.claude/skills/
```

Then just describe the task — the skill activates on its description — or invoke it
explicitly with `/<skill-name>`.

Building a server end-to-end? Paste the ready-made orchestration goal from
[docs/setup-prompt.md](docs/setup-prompt.md) — it drives all six skills in
dependency order with a verification gate after each phase.

## Skills

| Skill | Description |
| --- | --- |
| [mcp-server-design](skills/mcp-server-design/) | Design an MCP server's tool/resource/prompt surface: outcome-oriented tools, tool budget, naming, descriptions-as-prompts, flat typed schemas, pagination, agent-readable errors. |
| [mcp-server-implementation](skills/mcp-server-implementation/) | Implement MCP servers on the official TypeScript/Python SDKs: primitives, stdio + Streamable HTTP transports, lifecycle, error semantics, structured output, progress/cancellation. |
| [mcp-server-auth](skills/mcp-server-auth/) | Implement MCP authorization: OAuth 2.1 resource-server role, RFC 9728/8414 discovery, PKCE, RFC 8707 audience validation, scopes and step-up, client registration. |
| [mcp-server-security](skills/mcp-server-security/) | Harden MCP servers against MCP-specific attacks (tool poisoning, rug pulls, injection via results, SSRF, session hijacking) with guardrails-in-code, sandboxing, audit logging. |
| [mcp-server-testing](skills/mcp-server-testing/) | Test and evaluate MCP servers: Inspector, the official conformance suite, agent evals with verifiable answers, transcript-driven iteration, selection accuracy, CI gates, load tests. |
| [mcp-server-deployment](skills/mcp-server-deployment/) | Deploy, operate, and distribute MCP servers: stateless scaling, observability, health probes, canary rollouts, MCPB bundles, MCP Registry publishing, versioning. |

## Repository structure

```
skills/                  # distributed skills, one folder per skill (SKILL.md + evals/ + scripts/)
docs/                    # skill-authoring guide, eval methodology, deployment guide
scripts/                 # deterministic validator used by hooks and CI
skills.sh.json           # skills.sh repo-page customization (groupings)
.claude/                 # agentic dev setup: hooks + bundled add-skill / publish-repo skills
.claude-plugin/          # plugin + marketplace manifests (makes this repo installable)
.local/                  # gitignored working area: sources, research, PROMPT.md (see below)
```

## Working on this repo with an agent

This repo is agent-native: canonical agent instructions live in
[AGENTS.md](AGENTS.md) (CLAUDE.md imports it), hooks validate every `SKILL.md` on
write, `make check` runs the full validator, and CI enforces the same gate on every
PR. The bundled `add-skill` skill walks the eval-first authoring workflow described
in [docs/skill-authoring.md](docs/skill-authoring.md). Maintainers drive sessions
with their own (gitignored, personal) `.local/PROMPT.md` goal prompt.

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the skill-proposal
process, the authoring workflow, and the PR checklist. Please note the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Support

Questions, ideas, or something not working? Start with [SUPPORT.md](SUPPORT.md) —
bugs and skill proposals have [issue templates](../../issues/new/choose), and
security concerns go through [SECURITY.md](SECURITY.md) (never a public issue).

## License

[MIT](LICENSE) © 2026 Paldom
