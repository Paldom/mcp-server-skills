#!/usr/bin/env python3
"""Find stdout writes that corrupt MCP stdio framing.

Usage:
    python3 check_stdio_hygiene.py SRC_DIR [SRC_DIR...]

Scans first-party Python/JS/TS sources for writes to stdout — the #1 cause of
"works in terminal, Connection closed in the client". Skips dependency dirs
(node_modules, .venv, dist, build). Findings are printed as file:line and the
script exits 1 (triage each: route to stderr, a logger, or delete).

Heuristic, not a proof: it cannot see stdout writes inside dependencies or
dynamic calls. A clean run plus an MCP Inspector session is the real gate.
"""

import re
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".tox"}
PATTERNS = {
    ".py": [
        (re.compile(r"(?<![\w.])print\s*\((?![^)\n]*file\s*=\s*sys\.stderr)"), "print() without file=sys.stderr"),
        (re.compile(r"sys\.stdout\.write"), "sys.stdout.write"),
        (re.compile(r"logging\.basicConfig\((?![^)\n]*stream\s*=\s*sys\.stderr)[^)\n]*\)"),
         "logging.basicConfig without stream=sys.stderr (root logger defaults to stderr, but an explicit stdout handler elsewhere will break framing - verify)"),
    ],
    ".js": [
        (re.compile(r"console\.(log|info|debug|table)\s*\("), "console.log/info/debug (stdout) - use console.error"),
        (re.compile(r"process\.stdout\.write"), "process.stdout.write"),
    ],
}
PATTERNS[".ts"] = PATTERNS[".mjs"] = PATTERNS[".cjs"] = PATTERNS[".jsx"] = PATTERNS[".tsx"] = PATTERNS[".js"]


def scan(root: Path) -> list[str]:
    findings = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts) or path.suffix not in PATTERNS:
            continue
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as e:
            findings.append(f"{path}: unreadable ({e})")
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(("#", "//", "*")):
                continue
            for rx, why in PATTERNS[path.suffix]:
                if rx.search(line):
                    findings.append(f"{path}:{i}: {why}\n    {line.strip()[:120]}")
    return findings


def main() -> int:
    roots = [Path(a) for a in sys.argv[1:]] or None
    if not roots:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    all_findings = []
    for r in roots:
        if not r.exists():
            print(f"ERROR: no such path: {r}", file=sys.stderr)
            return 2
        all_findings += scan(r)
    for f in all_findings:
        print(f)
    n = len(all_findings)
    print(f"{'FAIL' if n else 'OK'}: {n} stdout-hygiene finding(s)")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
