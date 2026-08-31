#!/usr/bin/env python3
"""Lint a proposed MCP tool surface before implementation.

Usage:
    python3 lint_tool_surface.py TOOLS_JSON

TOOLS_JSON is a file containing either a JSON array of tool objects or an
object with a "tools" array. Each tool: {"name": ..., "description": ...,
"inputSchema": {...}} (inputSchema optional at design time).

Checks (spec revision 2025-11-25):
  E name matches ^[A-Za-z0-9_.-]{1,128}$ (SEP-986) and is unique
  E description present and >= 40 chars
  E inputSchema, when present, is an object type with typed properties
  W name not snake_case or missing a shared service prefix
  W description lacks when-to-use guidance ("use when"/"use this"/"not for")
  W tool count > 15 (split by domain/permission/performance)
  W schema nesting deeper than one object level (flatten)
  W constrained-looking string params without enum
Exit 1 on any E, else 0.
"""

import json
import re
import sys

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SNAKE_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
ENUMISH = ("status", "state", "type", "kind", "format", "mode", "level", "priority")

errors: list[str] = []
warnings: list[str] = []


def check_schema(tool: str, schema: dict) -> None:
    if schema.get("type") != "object":
        errors.append(f"{tool}: inputSchema.type must be 'object'")
        return
    props = schema.get("properties", {})
    for pname, p in props.items():
        if not isinstance(p, dict) or ("type" not in p and "enum" not in p):
            errors.append(f"{tool}.{pname}: property missing a type")
            continue
        if p.get("type") == "object":
            inner = p.get("properties", {})
            if any(isinstance(v, dict) and v.get("type") == "object" for v in inner.values()):
                warnings.append(
                    f"{tool}.{pname}: schema nested >1 level - flatten to top-level typed params"
                )
            elif not inner:
                warnings.append(
                    f"{tool}.{pname}: untyped object param - the model must guess its keys"
                )
        if p.get("type") == "string" and "enum" not in p and pname in ENUMISH:
            warnings.append(f"{tool}.{pname}: looks constrained ('{pname}') but has no enum")
    if "additionalProperties" not in schema:
        warnings.append(f"{tool}: consider additionalProperties:false to reject unknown fields")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read tools JSON: {e}", file=sys.stderr)
        return 2
    tools = data.get("tools", data) if isinstance(data, dict) else data
    if not isinstance(tools, list) or not tools:
        print('ERROR: expected a non-empty array of tools (or {"tools": [...]})', file=sys.stderr)
        return 2

    names = []
    for t in tools:
        name = t.get("name", "")
        names.append(name)
        if not NAME_RE.match(name):
            errors.append(
                f"{name or '<unnamed>'}: name must match [A-Za-z0-9_.-], 1-128 chars (SEP-986)"
            )
        elif not SNAKE_RE.match(name):
            warnings.append(
                f"{name}: not snake_case - tokenizers and clients handle snake_case best"
            )
        desc = (t.get("description") or "").strip()
        if len(desc) < 40:
            errors.append(
                f"{name}: description missing or <40 chars - descriptions are the model's routing prompt"
            )
        elif not re.search(r"\b(use (when|this|for)|not for|do not use)\b", desc, re.I):
            warnings.append(f"{name}: description has no when-to-use / not-for guidance")
        if isinstance(t.get("inputSchema"), dict):
            check_schema(name, t["inputSchema"])

    dupes = {n for n in names if names.count(n) > 1}
    for d in sorted(dupes):
        errors.append(f"{d}: duplicate tool name")
    if len(tools) > 15:
        warnings.append(
            f"{len(tools)} tools - above the ~5-15 heuristic; split by domain, permission, or performance profile"
        )
    prefixes = {n.split("_", 1)[0] for n in names if SNAKE_RE.match(n or "")}
    if len(tools) > 2 and len(prefixes) > 1:
        warnings.append(
            f"multiple name prefixes {sorted(prefixes)} - one shared service prefix avoids cross-server collisions"
        )

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(
        f"{'FAIL' if errors else 'OK'}: {len(errors)} error(s), {len(warnings)} warning(s) across {len(tools)} tool(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
