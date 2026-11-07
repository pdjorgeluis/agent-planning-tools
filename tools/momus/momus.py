#!/usr/bin/env python3
"""momus.py - Momus, an advisory spec reviewer.

Usage:
    momus.py [--backend NAME|none] [--allow DIR]... [--base DIR]... SPEC.md

Asks a model one question: could a capable developer start and finish this
spec? Advisory only: it never blocks and never decides. It writes nothing but
its own log. The script reads the files the spec cites (inside the allowed
roots, never secrets) and hands the model a bundle; every model backend runs
with NO tools.

First stdout line:
    [momus] backend=<name|none> model=<id|none> finish=<..> rung=<n>/<total>
Exit codes: 0 OKAY (or deterministic-only with no missing path), 10 ITERATE
(or deterministic-only with a missing path), 11 REJECT, 2 bad input, 3 failure.
"""

import argparse
import fnmatch
import hashlib
import os
import re
import sys

_HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_HERE)), "lib"))

from aptlib import backends, config, logs  # noqa: E402

TOOL = "momus"
DET_VERDICT = "VERDICT: NONE (deterministic only - no model judgment)"
EXIT_OK, EXIT_ITERATE, EXIT_REJECT, EXIT_USAGE, EXIT_FAILED = 0, 10, 11, 2, 3


class MomusError(Exception):
    """Fatal, user-facing error (printed without traceback)."""


def header_line(name="none", model="none", finish="n/a", rung=0, total=0):
    return f"[momus] backend={name} model={model} finish={finish} rung={rung}/{total}"


# ---------------------------------------------------------------- references

# Absolute (/...) or home (~/...) paths. The lookbehind rejects relative
# paths ("a/b", "./x") and URLs ("https://host/p": the '/' after ':' , after
# '/', and after the host's last word character are all refused).
_REF_RE = re.compile(
    r"(?<![\w:/.$-])((?:~/|/)[^\s`'\"<>()\[\]{}|,;]+)"
    r"(?:[ \t]+(?:lines?[ \t]+(\d+)(?:[ \t]*-[ \t]*(\d+))?"
    r"|L(\d+)(?:-L?(\d+))?))?"
)
_COLON_LINE_RE = re.compile(r"^(.*?):(\d+)(?:-(\d+))?(?::\d+)?$")
# A path wrapped in "...", '...' or `...` is ONE reference, spaces included.
# One line only, so an unmatched quote cannot swallow the rest of the file.
_QUOTED_RE = re.compile(
    r"(?<![\w])([\"'`])((?:~/|/)[^\"'`\n]+?)\1"
    r"(?::(\d+)(?:-(\d+))?|[ \t]+(?:lines?[ \t]+(\d+)(?:[ \t]*-[ \t]*(\d+))?"
    r"|L[ \t]*(\d+)(?:-L?(\d+))?))?"
)


class Ref:
    """One cited path: as written, plus an optional 1-based line range."""

    def __init__(self, written, lo=None, hi=None):
        self.written, self.lo, self.hi = written, lo, hi

    def key(self):
        return (self.written, self.lo, self.hi)

    def __repr__(self):
        return f"Ref({self.written!r}, {self.lo}, {self.hi})"


_NONPATH_CHARS = set("^$*?(){}|[]\\<>")
_LEAD_STRIP = "([{\"'`"
_TRAIL_STRIP = ")]}\"'`,;:."
_BARE_RE = re.compile(r"^[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.[A-Za-z0-9]{1,6}$")
_PSEUDO_ROOTS = ("/dev/", "/proc/", "/sys/")


def _is_nonpath(candidate):
    """R1: strip wrappers, then any regex/glob/placeholder char means 'not a path'."""
    core = candidate.lstrip(_LEAD_STRIP).rstrip(_TRAIL_STRIP)
    return any(c in _NONPATH_CHARS for c in core)


def _resolve_bare(token, bases):
    """R3: join a bare file name to each base; first existing join wins."""
    if not bases:
        return None
    lo = hi = None
    cm = _COLON_LINE_RE.match(token)
    if cm:
        token, lo = cm.group(1), int(cm.group(2))
        hi = int(cm.group(3)) if cm.group(3) else lo
    if not _BARE_RE.match(token):
        return None
    for base in bases:
        joined = os.path.join(os.path.abspath(os.path.expanduser(base)), token)
        if os.path.exists(joined):
            return joined, lo, hi
    return None


def extract_refs(text, bases=()):
    """Return ordered, de-duplicated Refs found in spec text (fences count).
    bases: directories used to resolve bare file names (R3)."""
    refs, seen = [], set()
    found = []  # (position, token, lo, hi)
    blanked = text
    for m in _QUOTED_RE.finditer(text):
        g = m.groups()
        nums = [x for x in g[2:] if x]
        lo = hi = None
        if nums:
            lo = int(nums[0])
            hi = int(nums[1]) if len(nums) > 1 else lo
        if not _is_nonpath(m.group(2)):
            found.append((m.start(), m.group(2).strip(), lo, hi))
        blanked = blanked[:m.start()] + " " * (m.end() - m.start()) + blanked[m.end():]
    # R1 on whole whitespace-delimited tokens, before any splitting; R3 bare names.
    scan = blanked
    for m in re.finditer(r"\S+", blanked):
        tok = m.group(0)
        if _is_nonpath(tok):
            scan = scan[:m.start()] + " " * len(tok) + scan[m.end():]
            continue
        core = tok.lstrip(_LEAD_STRIP).rstrip(_TRAIL_STRIP)
        if core and not core.startswith(("/", "~/")) and " " not in core:
            hit = _resolve_bare(core, bases)
            if hit:
                found.append((m.start(), hit[0], hit[1], hit[2]))
    for m in _REF_RE.finditer(scan):
        token = m.group(1).rstrip(".,:;*_!?")
        lo = hi = None
        cm = _COLON_LINE_RE.match(token)
        if cm:
            token, lo = cm.group(1), int(cm.group(2))
            hi = int(cm.group(3)) if cm.group(3) else lo
        elif m.group(2):
            lo = int(m.group(2))
            hi = int(m.group(3)) if m.group(3) else lo
        elif m.group(4):
            lo = int(m.group(4))
            hi = int(m.group(5)) if m.group(5) else lo
        found.append((m.start(), token, lo, hi))
    found.sort(key=lambda f: f[0])
    for _pos, token, lo, hi in found:
        if len(token) < 2 or "*" in token or "?" in token:
            continue
        if token.startswith(_PSEUDO_ROOTS):
            continue
        if lo is not None and hi < lo:
            lo, hi = hi, lo
        ref = Ref(token, lo, hi)
        if ref.key() not in seen:
            seen.add(ref.key())
            refs.append(ref)
    return refs


# ---------------------------------------------------------------- deterministic layer

def count_lines(path):
    with open(path, "rb") as f:
        return len(f.read().decode("utf-8", errors="replace").splitlines())


DENY_NAME_PATTERNS = (
    ".env", "*.env", ".env.*", "*token*", "*secret*", "*credential*",
    "auth.json", "id_rsa*", "id_ed25519*",
)
DENY_HOME_DIRS = (".ssh", ".gnupg")


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def deny_reason(raw, real):
    """Return why a path may never be read, or '' when no deny rule matches.
    Checks every component of the path as written AND of the resolved path."""
    home = os.path.expanduser("~")
    for dirname in DENY_HOME_DIRS:
        for base in (os.path.join(home, dirname), os.path.realpath(os.path.join(home, dirname))):
            if _under(real, base) or _under(os.path.abspath(raw), base):
                return f"under ~/{dirname}"
    seen = set()
    for source in (raw, real):
        for comp in source.split(os.sep):
            low = comp.lower()
            if not low or low in seen:
                continue
            seen.add(low)
            for pat in DENY_NAME_PATTERNS:
                if fnmatch.fnmatchcase(low, pat):
                    return f"matches deny pattern {pat}"
    return ""


def access(ref, roots):
    """Return (state, real, detail). state: DENIED, MISSING or READABLE.
    Pure path logic - nothing is opened here."""
    raw = os.path.expanduser(ref.written)
    real = os.path.realpath(raw)
    reason = deny_reason(raw, real)
    if reason:
        return "DENIED", real, reason
    inside = any(_under(real, r) for r in roots)
    if not inside and ".." in raw.split(os.sep):
        return "DENIED", real, "outside allowed roots (.. escape)"
    if not os.path.exists(real):
        return "MISSING", real, ""
    if not inside:
        return "DENIED", real, "outside allowed roots"
    return "READABLE", real, ""


def classify(ref, roots):
    """Return (status, detail). status: OK, MISSING, DENIED, EOF.
    Never reads a file unless it is allowed."""
    state, real, detail = access(ref, roots)
    if state != "READABLE":
        return state, detail
    if os.path.isdir(real):
        return "OK", "directory"
    if ref.lo is not None:
        try:
            n = count_lines(real)
        except OSError as e:
            return "MISSING", e.strerror
        if ref.lo > n:
            return "EOF", f"cites line {ref.lo}, file has {n} lines"
    return "OK", ""


EXCERPT_CONTEXT = 5
EXCERPT_DEFAULT_LINES = 80
MAX_READ_BYTES = 5 * 1024 * 1024


def build_bundle(spec_text, refs, roots):
    """Pre-bundle the model input (R10): spec as DATA, then one block per ref."""
    parts = ["=== SPEC ===\n" + spec_text]
    if not spec_text.endswith("\n"):
        parts[0] += "\n"
    for ref in refs:
        state, real, detail = access(ref, roots)
        if state == "DENIED":
            parts.append(f"=== DENIED {ref.written} ({detail}) ===\n")
        elif state == "MISSING":
            parts.append(f"=== MISSING {ref.written} ===\n")
        elif os.path.isdir(real):
            parts.append(f"=== FILE {real} (directory, not read) ===\n")
        else:
            try:
                with open(real, "rb") as f:
                    text = f.read(MAX_READ_BYTES).decode("utf-8", errors="replace")
            except OSError as e:
                parts.append(f"=== DENIED {ref.written} (unreadable: {e.strerror}) ===\n")
                continue
            lines = text.splitlines()
            n = len(lines)
            if ref.lo is None:
                a, b = (1, min(n, EXCERPT_DEFAULT_LINES)) if n else (0, 0)
            else:
                a, b = max(1, ref.lo - EXCERPT_CONTEXT), min(n, ref.hi + EXCERPT_CONTEXT)
            if ref.lo is not None and ref.lo > n:
                parts.append(f"=== FILE {real} (cites lines {ref.lo}-{ref.hi}; "
                             f"file has {n} lines) ===\n")
                continue
            body = "\n".join(lines[a - 1:b]) + "\n" if n else ""
            parts.append(f"=== FILE {real} (lines {a}-{b}) ===\n{body}")
    return "\n".join(parts)


def ref_label(ref):
    if ref.lo is None:
        return ref.written
    span = str(ref.lo) if ref.hi == ref.lo else f"{ref.lo}-{ref.hi}"
    return f"{ref.written}:{span}"


# ---------------------------------------------------------------- verdict parser (R4)

_VERDICT_RE = re.compile(r"^VERDICT: (OKAY|ITERATE|REJECT)$")
_ISSUE_RE = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")
MAX_ISSUES = 3


class Verdict:
    def __init__(self, verdict, summary, issues):
        self.verdict, self.summary, self.issues = verdict, summary, issues


def parse_verdict(reply):
    """Parse a model reply against R4. Return Verdict, or None (failed rung).

    The first non-empty line must be the verdict line (prose before it fails);
    a second VERDICT line later is ignored (first wins). Summary follows; a
    non-OKAY verdict needs `Issues:` with numbered lines, capped at 3.
    """
    lines = [ln.rstrip() for ln in (reply or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    m = _VERDICT_RE.match(lines[0])
    if not m:
        return None
    verdict = m.group(1)
    if not lines[1].startswith("Summary:") or not lines[1][len("Summary:"):].strip():
        return None
    summary = lines[1][len("Summary:"):].strip()
    issues = []
    if verdict != "OKAY":
        try:
            at = next(i for i, ln in enumerate(lines[2:], 2) if ln.strip() == "Issues:")
        except StopIteration:
            return None
        for ln in lines[at + 1:]:
            im = _ISSUE_RE.match(ln)
            if im:
                issues.append(im.group(2).strip())
        issues = issues[:MAX_ISSUES]
        if not issues:
            return None
    return Verdict(verdict, summary, issues)


def format_verdict(v):
    out = [f"VERDICT: {v.verdict}", f"Summary: {v.summary}"]
    if v.issues:
        out.append("Issues:")
        out.extend(f"{i}. {t}" for i, t in enumerate(v.issues, 1))
    return "\n".join(out)





VERDICT_EXIT = {"OKAY": EXIT_OK, "ITERATE": EXIT_ITERATE, "REJECT": EXIT_REJECT}


def read_prompt():
    path = os.path.expanduser(os.environ.get("APT_MOMUS_PROMPT")
                              or os.path.join(_HERE, "prompt.md"))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        raise MomusError(f"cannot read prompt file {path}: {e.strerror}")
    if not text.strip():
        raise MomusError(f"prompt file is empty: {path}")
    return text


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise MomusError(f"usage error: {message}")


def build_parser():
    p = _Parser(prog="momus.py", add_help=True,
                description="Momus - advisory spec reviewer.")
    p.add_argument("--backend", default=None, metavar="NAME|none",
                   help="use only this configured backend; 'none' skips every "
                        "model and runs the deterministic layer only")
    p.add_argument("--allow", action="append", default=[], metavar="DIR",
                   help="extra readable root (repeatable)")
    p.add_argument("--base", action="append", default=[], metavar="DIR",
                   help="resolve bare file names against DIR (repeatable, max 3); "
                        "also an allow root")
    p.add_argument("paths", nargs="*", metavar="SPEC.md")
    return p


def parse_args(argv):
    args = build_parser().parse_args(argv)
    if len(args.base) > 3:
        raise MomusError(f"usage error: at most 3 --base dirs, got {len(args.base)}")
    if len(args.paths) != 1:
        raise MomusError(
            f"usage error: exactly one SPEC.md path required, got {len(args.paths)}")
    spec = os.path.expanduser(args.paths[0])
    if not spec.lower().endswith(".md"):
        raise MomusError(f"usage error: spec must be a .md file: {args.paths[0]}")
    if os.path.isdir(spec):
        raise MomusError(f"usage error: spec is a directory, not a file: {args.paths[0]}")
    if not os.path.isfile(spec):
        raise MomusError(f"usage error: spec file not found: {args.paths[0]}")
    args.spec = spec
    return args


def read_spec(path):
    """Return (text, sha256-of-raw-bytes). Non-UTF-8 bytes are replaced."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise MomusError(f"usage error: cannot read spec {path}: {e.strerror}")
    return raw.decode("utf-8", errors="replace"), hashlib.sha256(raw).hexdigest()


def readable_roots(args):
    return [os.path.realpath(os.path.dirname(os.path.abspath(args.spec)))] + [
        os.path.realpath(os.path.expanduser(d)) for d in args.allow + args.base]


def log_entry(cfg, args, spec_sha, backend, verdict, issues):
    logs.append(cfg.log_dir, TOOL, os.path.basename(args.spec),
                {"Spec": os.path.abspath(args.spec), "Spec sha256": spec_sha,
                 "Backend": backend, "Verdict": verdict, "Issues": issues})


def run_det(cfg, args, spec_text, spec_sha):
    roots = readable_roots(args)
    refs = extract_refs(spec_text, args.base)
    lines, problems = [], 0
    for ref in refs:
        status, detail = classify(ref, roots)
        label = ref_label(ref)
        if status == "OK":
            lines.append(f"- OK {label}" + (f" ({detail})" if detail else ""))
        elif status == "MISSING":
            lines.append(f"- MISSING {label}")
            problems += 1
        elif status == "EOF":
            lines.append(f"- LINE BEYOND EOF {label}: {detail}")
            problems += 1
        else:
            lines.append(f"- DENIED {label} ({detail})")
    print(header_line(total=len(cfg.rungs)))
    print(DET_VERDICT)
    print(f"Summary: {len(refs)} reference(s) checked, {problems} problem(s).")
    if lines:
        print("Findings:")
        print("\n".join(lines))
    log_entry(cfg, args, spec_sha, "none", "NONE", problems)
    return EXIT_ITERATE if problems else EXIT_OK


def run_models(cfg, args, spec_text, spec_sha, rungs):
    try:
        system_prompt = read_prompt()
    except MomusError as e:
        print(f"[momus] {e}", file=sys.stderr)
        return EXIT_FAILED
    bundle = build_bundle(spec_text, extract_refs(spec_text, args.base),
                          readable_roots(args))
    reply, causes = backends.run_ladder(
        cfg, rungs, system_prompt, bundle,
        validate=lambda t: parse_verdict(t) is not None)
    for cause in causes:
        print(f"[momus] backend failed: {cause}", file=sys.stderr)
    if reply is None:
        print("[momus] no model backend answered; deterministic layer only",
              file=sys.stderr)
        return run_det(cfg, args, spec_text, spec_sha)
    verdict = parse_verdict(reply.text)
    print(header_line(reply.name, reply.model, reply.finish, reply.number, reply.total))
    print(format_verdict(verdict))
    log_entry(cfg, args, spec_sha, f"{reply.number}/{reply.total} {reply.name}",
              verdict.verdict, len(verdict.issues))
    return VERDICT_EXIT[verdict.verdict]


def run(argv=None):
    if os.name == "nt":
        print("[momus] Windows is not supported", file=sys.stderr)
        return EXIT_USAGE
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        spec_text, spec_sha = read_spec(args.spec)
        cfg = config.load()
    except (MomusError, config.ConfigError) as e:
        print(f"[momus] {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        name = args.backend or os.environ.get("APT_BACKEND") or None
        if name == "none":
            return run_det(cfg, args, spec_text, spec_sha)
        rungs = config.select(cfg, name)
        if name and not rungs:
            print(f"[momus] usage error: no configured backend named {name!r}",
                  file=sys.stderr)
            return EXIT_USAGE
        if not rungs:
            for cause in cfg.invalid:
                print(f"[momus] backend failed: {cause}", file=sys.stderr)
            print("[momus] no backend configured; deterministic layer only "
                  "(see config.example.toml)", file=sys.stderr)
            return run_det(cfg, args, spec_text, spec_sha)
        return run_models(cfg, args, spec_text, spec_sha, rungs)
    except Exception as e:  # last resort: report, never traceback
        print(f"[momus] failure: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_FAILED


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
