#!/usr/bin/env python3
"""privacy-scan.py - fail if private data or secret-looking text is in the repo.

    python3 scripts/privacy-scan.py [--terms-file FILE] [--root DIR]

Scans every tracked or untracked non-ignored file, and the patch bodies of
`git log -p --format=` (commit headers excluded). Fails (exit 1) when it finds
a term from the terms file (one per line, case-insensitive; the file is
supplied by the maintainer and is never stored in the repo) or a secret-looking
pattern. Findings print as `file:line: kind` and never echo the matched text.
Exit 0 clean, 1 findings, 2 usage error.

Every pattern is assembled at run time from fragments, so this file contains
none of the literals it forbids.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = "".join

PATTERNS = (
    ("private key header", re.compile(J(["-----BEGIN ", "[A-Z ]*", "PRIVATE ", "KEY"]))),
    ("secret key prefix (sk)", re.compile(J([r"\b", "s", "k-", r"[A-Za-z0-9_\-]{8,}"]))),
    ("github token prefix", re.compile(J([r"\b(?:", "gh", "[pousr]_", r"[A-Za-z0-9]{10,}|",
                                         "github_", "pat_", r"[A-Za-z0-9_]{10,})"]))),
    ("slack token prefix", re.compile(J([r"\b", "x", "ox", r"[abposr]-[A-Za-z0-9-]{8,}"]))),
    ("long token near a secret word",
     re.compile(J([r"(?i)(?:key|token|secret|pass", "word", r")\w*[\"']?\s*[:=]\s*[\"']?",
                   r"[A-Za-z0-9+/=_\-]{32,}"]))),
    ("home directory path", re.compile(J([r"/ho", "me/", r"[A-Za-z0-9_.\-]+"]))),
    ("email address", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("private IPv4 address", re.compile(
        J([r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|",
           r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"]))),
    ("8-10 digit id", re.compile(r"\b\d{8,10}\b")),
)
SKIP_DIRS = {".git", "__pycache__"}


class UsageError(Exception):
    pass


def load_terms(path):
    try:
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as f:
            terms = [t.strip().lower() for t in f if t.strip()]
    except OSError as exc:
        raise UsageError(f"cannot read terms file: {exc.strerror}")
    if not terms:
        raise UsageError("terms file has no terms")
    return terms


def scan_text(label, text, terms, findings):
    """Append (label, lineno, kind) for each hit. Never records matched text."""
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for i, term in enumerate(terms, 1):
            if term in low:
                findings.append((label, n, f"forbidden term #{i}"))
        for kind, rx in PATTERNS:
            if rx.search(line):
                findings.append((label, n, kind))


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=120)


def list_files(root):
    p = git(root, "ls-files", "-co", "--exclude-standard", "-z")
    if p.returncode == 0:
        return sorted(f for f in p.stdout.decode("utf-8", "replace").split("\0") if f), True
    out = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        out += [os.path.relpath(os.path.join(d, n), root) for n in names]
    return sorted(out), False


def scan_history(root, terms, findings):
    p = git(root, "log", "-p", "--format=")
    if p.returncode != 0:
        return
    current = "?"
    for n, line in enumerate(p.stdout.decode("utf-8", "replace").splitlines(), 1):
        if line.startswith("diff --git "):
            current = line.split(" b/", 1)[-1]
            continue
        if line.startswith(("index ", "--- ", "+++ ", "new file", "deleted file",
                            "similarity", "rename ")):
            continue
        tmp = []
        scan_text(f"history:{current}", line, terms, tmp)
        findings += [(label, n, kind) for label, _ln, kind in tmp]


def run(root, terms_file):
    terms = load_terms(terms_file) if terms_file else []
    if not terms:
        print("privacy-scan: no terms file; pattern checks only", file=sys.stderr)
    findings = []
    files, is_git = list_files(root)
    for rel in files:
        tmp = []
        scan_text(rel, rel, terms, tmp)
        findings += [(rel, 0, kind) for _l, _n, kind in tmp if kind.startswith("forbidden")]  # path text
        path = os.path.join(root, rel)
        try:
            with open(path, "rb") as f:
                text = f.read().decode("utf-8", "replace")
        except OSError:
            continue
        scan_text(rel, text, terms, findings)
    if is_git:
        scan_history(root, terms, findings)
    seen = set()
    for label, n, kind in findings:
        if (label, n, kind) not in seen:
            seen.add((label, n, kind))
            print(f"{label}:{n}: {kind}")
    if seen:
        print(f"privacy-scan: FAILED ({len(seen)} finding(s))")
        return 1
    print(f"privacy-scan: clean ({len(files)} file(s){', history' if is_git else ''})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="privacy-scan.py")
    p.add_argument("--terms-file", default=os.environ.get("APT_TERMS_FILE"))
    p.add_argument("--root", default=ROOT_DEFAULT)
    args = p.parse_args(argv)
    try:
        return run(os.path.abspath(args.root), args.terms_file)
    except UsageError as exc:
        print(f"privacy-scan: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
