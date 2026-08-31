#!/usr/bin/env python3
"""Probe an MCP server's OAuth discovery surface (RFC 9728 + RFC 8414/OIDC).

Usage:
    python3 check_auth_endpoints.py SERVER_URL [--insecure]

SERVER_URL is the MCP endpoint (e.g. https://host/mcp or http://127.0.0.1:3000/mcp).
Read-only probes, no credentials sent:
  1. POST without a token           -> expect 401 with a WWW-Authenticate Bearer
                                       challenge (resource_metadata= is the good path)
  2. PRM well-known                 -> expect JSON with resource + authorization_servers;
                                       resource should match the server URL
  3. each authorization server     -> RFC 8414 or OIDC metadata reachable;
                                       code_challenge_methods_supported includes S256
Exit 1 on any FAIL, else 0. --insecure skips TLS verification (local dev only).
"""

import json
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

results: list[tuple[bool, str]] = []


def report(ok: bool, msg: str) -> None:
    results.append((ok, msg))
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")


def fetch(
    url: str, ctx, method: str = "GET", body: bytes | None = None, headers: dict | None = None
):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})  # noqa: S310 - fixed http(s) endpoint, not a caller-supplied scheme
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:  # noqa: S310 - fixed http(s) endpoint, not a caller-supplied scheme
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as e:
        return None, {}, str(e).encode()


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--insecure"]
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    server = args[0].rstrip("/")
    ctx = ssl._create_unverified_context() if "--insecure" in sys.argv else None  # noqa: S323 - only when the caller passes --insecure; the default context verifies
    parts = urlsplit(server)
    origin = f"{parts.scheme}://{parts.netloc}"

    # 1. Unauthenticated request
    status, headers, _ = fetch(
        server,
        ctx,
        "POST",
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "auth-probe", "version": "0"},
                },
            }
        ).encode(),
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    if status is None:
        report(False, f"server unreachable: {server}")
    elif status == 401:
        challenge = headers.get("WWW-Authenticate", "")
        report(True, "unauthenticated request -> 401")
        if "resource_metadata=" in challenge:
            report(True, "WWW-Authenticate advertises resource_metadata")
        else:
            report(
                bool(challenge),
                f"WWW-Authenticate: {challenge!r} (no resource_metadata= - clients must fall back to well-known)",
            )
    else:
        report(
            False, f"unauthenticated request -> {status} (expected 401; is auth actually enforced?)"
        )

    # 2. Protected resource metadata
    prm = None
    path_suffix = parts.path.rstrip("/")
    candidates = [
        f"{origin}/.well-known/oauth-protected-resource{path_suffix}",
        f"{origin}/.well-known/oauth-protected-resource",
    ]
    for url in candidates:
        status, _, body = fetch(url, ctx)
        if status == 200:
            try:
                prm = json.loads(body)
            except json.JSONDecodeError:
                report(False, f"PRM at {url} is not valid JSON")
                break
            report(True, f"PRM found at {url}")
            break
    if prm is None:
        report(False, f"no protected resource metadata at {' or '.join(candidates)}")
    else:
        resource = prm.get("resource", "")
        report(bool(resource), f"PRM resource = {resource!r}")
        if resource and resource.rstrip("/") != server:
            report(
                False,
                f"PRM resource does not match probed URL {server} - audience validation will misfire",
            )
        servers = prm.get("authorization_servers") or []
        report(bool(servers), f"authorization_servers = {servers}")

        # 3. AS metadata
        for as_url in servers:
            as_url = as_url.rstrip("/")
            meta = None
            for wk in (
                f"{as_url}/.well-known/oauth-authorization-server",
                f"{as_url}/.well-known/openid-configuration",
            ):
                status, _, body = fetch(wk, ctx)
                if status == 200:
                    try:
                        meta = json.loads(body)
                        report(True, f"AS metadata at {wk}")
                    except json.JSONDecodeError:
                        report(False, f"AS metadata at {wk} is not valid JSON")
                    break
            if meta is None:
                report(False, f"no AS metadata under {as_url}")
                continue
            if meta.get("issuer", "").rstrip("/") != as_url:
                report(
                    False,
                    f"AS issuer {meta.get('issuer')!r} != metadata origin {as_url} (RFC 8414 s3.3)",
                )
            methods = meta.get("code_challenge_methods_supported") or []
            report(
                "S256" in methods,
                f"code_challenge_methods_supported = {methods} (clients MUST refuse an AS without S256 here)",
            )

    fails = sum(1 for ok, _ in results if not ok)
    print(f"{'FAIL' if fails else 'OK'}: {fails} failure(s) across {len(results)} check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
