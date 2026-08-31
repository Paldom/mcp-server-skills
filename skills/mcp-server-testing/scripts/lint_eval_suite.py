#!/usr/bin/env python3
"""Lint an MCP agent-eval suite (XML <evaluation> or JSON list of qa pairs).

Usage:
    python3 lint_eval_suite.py SUITE_FILE [--min 10]

Checks:
  E parseable; >= --min qa pairs (default 10)
  E every question and answer non-empty
  E no duplicate questions or answers (duplicate answers let one lucky guess
    score twice; vary answer modalities)
  E answer leaked verbatim inside its own question
  W instability words in questions (current, latest, today, now, this week/
    month/year, how many ... are there) - answers must be historically stable
  W question lacks a declared answer format ("Answer format:", "format:",
    "True or False", "YYYY")
  W answer looks like a list/JSON (single string-comparable values only)
Exit 1 on any E, else 0.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

UNSTABLE = re.compile(
    r"\b(current(ly)?|latest|today|right now|as of now|this (week|month|year)|how many .* are there)\b",
    re.I,
)
FORMAT_HINT = re.compile(
    r"(answer format|format:|true or false|yes or no|YYYY|\bMM\b|\bDD\b)", re.I
)


def load_pairs(path: Path):
    text = path.read_text(errors="replace")
    if path.suffix.lower() == ".json" or text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        items = data if isinstance(data, list) else data.get("qa_pairs") or data.get("cases") or []
        return [(str(i.get("question", "")), str(i.get("answer", ""))) for i in items]
    root = ET.fromstring(text)  # noqa: S314 - parses a local file the caller supplies; defusedxml would add a runtime dependency a skill must not have
    return [
        ((p.findtext("question") or "").strip(), (p.findtext("answer") or "").strip())
        for p in root.iter("qa_pair")
    ]


def main() -> int:
    args = sys.argv[1:]
    min_n = 10
    if "--min" in args:
        i = args.index("--min")
        min_n = int(args[i + 1])
        del args[i : i + 2]
    if len(args) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    path = Path(args[0])
    try:
        pairs = load_pairs(path)
    except (OSError, json.JSONDecodeError, ET.ParseError) as e:
        print(f"ERROR unparseable suite: {e}")
        return 1

    errors, warnings = [], []
    if len(pairs) < min_n:
        errors.append(f"only {len(pairs)} qa pair(s); need >= {min_n}")
    seen_q, seen_a = {}, {}
    for n, (q, a) in enumerate(pairs, 1):
        tag = f"qa#{n}"
        if not q.strip():
            errors.append(f"{tag}: empty question")
            continue
        if not a.strip():
            errors.append(f"{tag}: empty answer")
            continue
        qn, an = " ".join(q.split()).lower(), " ".join(a.split()).lower()
        if qn in seen_q:
            errors.append(f"{tag}: duplicate of qa#{seen_q[qn]}")
        seen_q.setdefault(qn, n)
        if an in seen_a:
            errors.append(
                f"{tag}: duplicate answer of qa#{seen_a[an]} ({a!r}) - vary answer modalities"
            )
        seen_a.setdefault(an, n)
        if len(an) > 3 and an in qn:
            errors.append(f"{tag}: answer appears verbatim in the question")
        m = UNSTABLE.search(q)
        if m:
            warnings.append(
                f"{tag}: unstable phrasing {m.group(0)!r} - pin a historical window instead"
            )
        if not FORMAT_HINT.search(q):
            warnings.append(
                f"{tag}: no declared answer format (add e.g. 'Answer format: YYYY-MM-DD')"
            )
        if a.strip().startswith(("[", "{")) or ("," in a and len(a) > 40):
            warnings.append(
                f"{tag}: answer looks like a list/structure - use one string-comparable value"
            )

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(
        f"{'FAIL' if errors else 'OK'}: {len(errors)} error(s), {len(warnings)} warning(s), {len(pairs)} pair(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
