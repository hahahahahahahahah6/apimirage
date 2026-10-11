#!/usr/bin/env python3
"""Create files in hahahahahahahahah6/ghostapi via the Contents API (PUT per file).

Usage: python3 push_contents.py [--dry-run]
Reads the same credential plumbing as the github skill's gh-api.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import os
import sys
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import dynamic_credentials as dc

OWNER = "hahahahahahahahah6"
REPO = "ghostapi"
BASE = "https://api.github.com"
CREDENTIAL_NAME = "custom.github2"
ALLOWED_HOSTS = ["api.github.com"]
ROOT = os.path.expanduser("~/workspace/ghostapi")

FILES = [
    "README.md",
    "LICENSE",
    "pyproject.toml",
    ".gitignore",
    "src/ghostapi/__init__.py",
    "src/ghostapi/checker.py",
    "src/ghostapi/cli.py",
    "tests/test_ghostapi.py",
    "tests/fixtures/fakelib/__init__.py",
]

FORBIDDEN_NAMES = {"PLAN.md", "promo-drafts.md", "devto-article.md"}
SENSITIVE_HINTS = (".env", "credentials", "secret", "token", ".pem", ".key")


def load_gitignore_patterns():
    patterns = []
    p = os.path.join(ROOT, ".gitignore")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def ignored(rel, patterns):
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(os.path.basename(rel), pat):
            return pat
    return None


def api(method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=body, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "muse-github-skill/1.0",
            "Content-Type": "application/json",
        },
    )
    dc.add_surrogate_to_request(req, CREDENTIAL_NAME, allowed_hosts=ALLOWED_HOSTS)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} on {method} {path}: {exc.read().decode()[:300]}",
              file=sys.stderr)
        raise SystemExit(1)
    return dc.read_json_response(resp)


def main():
    dry = "--dry-run" in sys.argv
    patterns = load_gitignore_patterns()

    print("== dry-run: file list vs .gitignore ==")
    for rel in FILES:
        base = os.path.basename(rel)
        if base in FORBIDDEN_NAMES:
            print(f"  BLOCKED (forbidden name): {rel}")
            raise SystemExit(1)
        if any(h in base.lower() for h in SENSITIVE_HINTS):
            print(f"  BLOCKED (sensitive hint): {rel}")
            raise SystemExit(1)
        pat = ignored(rel, patterns)
        if pat:
            print(f"  BLOCKED (gitignored by '{pat}'): {rel}")
            raise SystemExit(1)
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            print(f"  MISSING: {rel}")
            raise SystemExit(1)
        print(f"  ok: {rel}")
    print("dry-run clean: no forbidden / sensitive / gitignored files.")
    if dry:
        return

    for rel in FILES:
        with open(os.path.join(ROOT, rel), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        data = api("PUT", f"/repos/{OWNER}/{REPO}/contents/{rel}", {
            "message": f"add {rel}",
            "content": content,
        })
        print(f"pushed {rel} -> {data['content']['sha'][:8]}")


if __name__ == "__main__":
    main()
