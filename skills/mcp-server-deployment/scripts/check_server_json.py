#!/usr/bin/env python3
"""Gate an MCP Registry server.json before `mcp-publisher publish`.

Usage:
    python3 check_server_json.py SERVER_JSON [--package-json PATH]

Checks (registry preview, schema 2025-12-11 era - re-verify fields at
https://modelcontextprotocol.io/registry/quickstart when publishing):
  E parseable JSON with name, description, version
  E name is reverse-DNS namespaced (io.github.<owner>/<server> or com.example/<server>)
  E at least one of packages[] / remotes[]
  E every package has registryType, identifier, version; every remote has type+https url
  E remote type is a known transport ("streamable-http" or legacy "sse")
  W version not semver-shaped; description > 100 chars or < 20
  W schema field missing or not a static.modelcontextprotocol.io URL
  W env vars that look secret without isSecret: true
  E --package-json given and its mcpName != server.json name
Exit 1 on any E, else 0.
"""

import json
import re
import sys
from pathlib import Path

errors: list[str] = []
warnings: list[str] = []


def main() -> int:
    args = sys.argv[1:]
    pkg_path = None
    if "--package-json" in args:
        i = args.index("--package-json")
        pkg_path = Path(args[i + 1])
        del args[i : i + 2]
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        sj = json.loads(Path(args[0]).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR cannot read server.json: {e}")
        return 1

    name = sj.get("name", "")
    if not name:
        errors.append("missing name")
    elif not re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z0-9.-]+/[A-Za-z0-9._-]+$", name):
        errors.append(f"name {name!r} is not reverse-DNS namespaced (e.g. io.github.you/server)")
    desc = sj.get("description", "")
    if not desc:
        errors.append("missing description")
    elif not 20 <= len(desc) <= 100:
        warnings.append(
            f"description length {len(desc)} - registry listings read best at 20-100 chars"
        )
    if not sj.get("version"):
        errors.append("missing version")
    elif not re.match(r"^\d+\.\d+\.\d+", str(sj["version"])):
        warnings.append(f"version {sj['version']!r} is not semver-shaped")
    schema = sj.get("$schema", "")
    if "static.modelcontextprotocol.io/schemas/" not in schema:
        warnings.append("$schema missing or not the official schema URL - pin one to catch drift")

    packages = sj.get("packages") or []
    remotes = sj.get("remotes") or []
    if not packages and not remotes:
        errors.append("neither packages[] nor remotes[] present - nothing to install")
    for i, p in enumerate(packages):
        for field in ("registryType", "identifier", "version"):
            if not p.get(field):
                errors.append(f"packages[{i}]: missing {field}")
        for ev in p.get("environmentVariables") or []:
            n = ev.get("name", "")
            if re.search(r"(?i)key|token|secret|password", n) and not ev.get("isSecret"):
                warnings.append(f"packages[{i}] env {n}: looks secret but isSecret is not true")
    for i, r in enumerate(remotes):
        rtype = r.get("type", "")
        if rtype not in {"streamable-http", "sse"}:
            errors.append(f"remotes[{i}]: unknown transport type {rtype!r}")
        elif rtype == "sse":
            warnings.append(f"remotes[{i}]: sse transport is deprecated - prefer streamable-http")
        url = r.get("url", "")
        if not url.startswith("https://"):
            errors.append(f"remotes[{i}]: url must be https ({url!r})")

    if pkg_path:
        try:
            pkg = json.loads(pkg_path.read_text())
            if pkg.get("mcpName") != name:
                errors.append(
                    f"package.json mcpName {pkg.get('mcpName')!r} != server.json name {name!r} (registry verification fails)"
                )
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"cannot read --package-json: {e}")

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{'FAIL' if errors else 'OK'}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
