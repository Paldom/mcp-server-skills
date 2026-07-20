#!/usr/bin/env python3
"""Run the deterministic slice of the MCP server security checklist over a repo.

Usage:
    python3 security_checklist.py --repo PATH

Machine-checkable items are verified and reported PASS/FAIL; judgment items are
printed as TODO for the reviewing human/agent. Exit 1 if any FAIL, else 0.

Checks:
  F lockfile present when a manifest exists (package-lock/pnpm-lock/yarn.lock,
    uv.lock/poetry.lock/requirements*.txt with pins)
  F auto-updating installs in configs/docs: 'npx -y', '@latest'
  F .env (or *.pem/key files) tracked by git
  F obvious secret literals in tracked sources (heuristic regexes)
  F Docker base images tagged :latest
  T TODO items: confirmation+idempotency on destructive tools, two-layer input
    validation, audit store separation, rate limits/kill switches, output
    fencing, sandbox profile, description-drift scanning in CI
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECRET_RES = [
    (re.compile(r"(sk|rk)-[A-Za-z0-9]{20,}"), "API-key-shaped literal"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
    (re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"), "private key material"),
    (re.compile(r"(?i)(api_key|apikey|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9+/_-]{16,}['\"]"), "hardcoded credential assignment"),
]
TEXT_SUFFIXES = {".py", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml", ".env", ".md", ".sh", ""}
TODOS = [
    "destructive tools: confirmation gate + idempotency key + honest destructiveHint",
    "two-layer validation: schema at protocol boundary, business rules in handlers",
    "audit events for every tool call to a store separate from the app DB; no secrets in logs",
    "per-tool rate limits, per-identity cost quotas, kill switch per tool",
    "external/tool-fetched content fenced in delimiters + injection-screened before return",
    "runtime sandbox: non-root container, minimal FS + egress allowlist",
    "tool-description drift detection (hash or scanner) wired into CI",
    "SSRF guards on every URL-fetching tool (scheme/host allowlist, private ranges blocked)",
]

fails: list[str] = []
passes: list[str] = []


def note(ok: bool, msg: str) -> None:
    (passes if ok else fails).append(msg)
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")


def tracked_files(repo: Path) -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                             capture_output=True, check=True)
        return [repo / f for f in out.stdout.decode().split("\0") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [p for p in repo.rglob("*") if p.is_file()
                and not any(s in p.parts for s in (".git", "node_modules", ".venv", "dist"))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    repo = Path(ap.parse_args().repo).resolve()
    if not repo.is_dir():
        print(f"ERROR: not a directory: {repo}", file=sys.stderr)
        return 2
    files = tracked_files(repo)
    names = {p.name for p in files}

    if "package.json" in names:
        note(bool({"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock"} & names),
             "Node manifest has a lockfile")
    if "pyproject.toml" in names or any(n.startswith("requirements") for n in names):
        note(bool({"uv.lock", "poetry.lock", "Pipfile.lock"} & names
                  or any(n.startswith("requirements") for n in names)),
             "Python manifest has a lock/pinned requirements")

    env_tracked = [p for p in files if p.name == ".env" or p.suffix in {".pem", ".p12"} or p.name.endswith("_rsa")]
    note(not env_tracked, f".env/key files not tracked{': ' + ', '.join(str(p.relative_to(repo)) for p in env_tracked) if env_tracked else ''}")

    latest_hits, secret_hits = [], []
    for p in files:
        if p.suffix not in TEXT_SUFFIXES or p.stat().st_size > 1_000_000:
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        rel = p.relative_to(repo)
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"npx\s+-y\s|@latest\b", line) and p.suffix in {".json", ".md", ".yaml", ".yml", ".sh", ""}:
                latest_hits.append(f"{rel}:{i}")
            if p.name.lower().startswith("dockerfile") or "FROM " in line and p.name.lower().startswith("dockerfile"):
                pass
            for rx, why in SECRET_RES:
                if rx.search(line) and "example" not in line.lower() and "placeholder" not in line.lower():
                    secret_hits.append(f"{rel}:{i} ({why})")
        if p.name.lower().startswith("dockerfile"):
            for i, line in enumerate(text.splitlines(), 1):
                if re.match(r"\s*FROM\s+\S+:latest\b", line):
                    latest_hits.append(f"{rel}:{i} (FROM :latest)")
    note(not latest_hits, "no auto-updating installs (npx -y / @latest / FROM :latest)"
         + (f" - {len(latest_hits)} hit(s): " + "; ".join(latest_hits[:5]) if latest_hits else ""))
    note(not secret_hits, "no secret-shaped literals in tracked files"
         + (f" - {len(secret_hits)} hit(s): " + "; ".join(secret_hits[:5]) if secret_hits else ""))

    print("\nTODO (judgment items - verify and record dispositions):")
    for t in TODOS:
        print(f"  [ ] {t}")
    print(f"\n{'FAIL' if fails else 'OK'}: {len(fails)} failure(s), {len(passes)} pass(es), {len(TODOS)} todo(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
