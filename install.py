#!/usr/bin/env python3
"""install.py - install agent-planning-tools (Metis and/or Momus).

    python3 install.py --tools metis|momus|all
                       [--target hermes|claude-code|codex|opencode|generic]
                       [--prefix DIR] [--dry-run] [--uninstall] [--yes]

Copies only the chosen tools plus lib/aptlib into PREFIX (default
$XDG_DATA_HOME/agent-planning-tools), writes the skill or instruction file for
the target, and prints a manifest of what it wrote. An existing file that
differs is never overwritten without --yes; with --yes it is first backed up
as <file>.bak-<timestamp>. --uninstall removes only files named in the
manifest (PREFIX/.apt-manifest.json).

Tested on Hermes only; other targets follow the vendors' documented
conventions and are untested. Windows is not supported.
"""

import argparse
import hashlib
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.realpath(__file__))
MANIFEST = ".apt-manifest.json"
TOOLS = ("metis", "momus")
TARGETS = ("hermes", "claude-code", "codex", "opencode", "generic")
LIB_FILES = ("__init__.py", "config.py", "backends.py", "logs.py")
TOOL_FILES = {"metis": ("metis.py", "prompt.md", "context.example.md", "SKILL.md"),
              "momus": ("momus.py", "prompt.md", "SKILL.md")}

# Where each target's file goes, relative to the target root (the prefix when
# --prefix is given, else the home directory). kind: skill = the tool's
# SKILL.md; snippet = an AGENTS.md-style snippet the user includes by hand
# (existing instruction files are never edited). Locations are vendors'
# conventions as we understand them: UNVERIFIED until docs/TARGETS.md says so.
TARGET_LAYOUT = {
    "hermes": ("skill", ".hermes/skills/{tool}/SKILL.md"),
    "claude-code": ("skill", ".claude/skills/{tool}/SKILL.md"),
    "codex": ("snippet", ".codex/agent-planning-tools.md"),
    "opencode": ("snippet", ".config/opencode/agent-planning-tools.md"),
    "generic": ("snippet", "agent-planning-tools-AGENTS.md"),
}

SNIPPET = """# agent-planning-tools (advisory planning helpers)

Tested on Hermes only; other targets follow the vendors' documented
conventions and are untested.

{items}
Both tools are advisory: they never block and never decide. Never put secrets
in a request or a spec.
"""
SNIPPET_ITEMS = {
    "metis": ("- Metis, before planning an ambiguous or complex request:\n"
              "  `python3 {root}/tools/metis/metis.py \"<request>\"`\n"),
    "momus": ("- Momus, on a drafted multi-step, irreversible or expensive spec:\n"
              "  `python3 {root}/tools/momus/momus.py --allow <dir> SPEC.md`\n"
              "  (exit 0 OKAY, 10 ITERATE, 11 REJECT).\n"),
}


class InstallError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_repo(rel):
    path = os.path.join(REPO, *rel.split("/"))
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        raise InstallError(f"missing source file {rel}: {exc.strerror}")


def default_prefix(env):
    base = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "agent-planning-tools")


def plan_files(tools, target, prefix, explicit_prefix, env=None):
    """Return the ordered [(dest_path, bytes, tool)] to write."""
    env = os.environ if env is None else env
    root = os.path.abspath(prefix)
    files = [(os.path.join(root, "LICENSE"), read_repo("LICENSE"), "shared"),
             (os.path.join(root, "config.example.toml"), read_repo("config.example.toml"), "shared")]
    if os.path.exists(os.path.join(REPO, "NOTICE.md")):
        files.append((os.path.join(root, "NOTICE.md"), read_repo("NOTICE.md"), "shared"))
    for name in LIB_FILES:
        files.append((os.path.join(root, "lib", "aptlib", name),
                      read_repo(f"lib/aptlib/{name}"), "shared"))
    for tool in tools:
        for name in TOOL_FILES[tool]:
            files.append((os.path.join(root, "tools", tool, name),
                          read_repo(f"tools/{tool}/{name}"), tool))
    kind, rel = TARGET_LAYOUT[target]
    troot = root if explicit_prefix else os.path.expanduser("~")
    if kind == "skill":
        for tool in tools:
            text = read_repo(f"tools/{tool}/SKILL.md").decode("utf-8", "replace")
            text = text.replace("{{APT_ROOT}}", root)
            files.append((os.path.join(troot, *rel.format(tool=tool).split("/")),
                          text.encode("utf-8"), tool))
    else:
        items = "".join(SNIPPET_ITEMS[t].format(root=root) for t in tools)
        files.append((os.path.join(troot, *rel.split("/")),
                      SNIPPET.format(items=items).encode("utf-8"), "target"))
    return files


def load_manifest(root):
    path = os.path.join(root, MANIFEST)
    if not os.path.exists(path):
        return {"files": [], "dirs": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("files"), list) and isinstance(data.get("dirs"), list):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    raise InstallError(f"unreadable manifest {path}; refusing to touch anything")


def _missing_dirs(path, stop):
    """Directories that do not exist yet between ``stop`` and path's parent."""
    out, d = [], os.path.dirname(path)
    while d and not os.path.isdir(d):
        out.append(d)
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return out


def install(tools, target, prefix, explicit_prefix, dry_run, yes, out=print):
    root = os.path.abspath(prefix)
    manifest = load_manifest(root)
    known = {e["path"]: e for e in manifest["files"]}
    dirs = list(manifest["dirs"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    skipped = planned = 0
    out(f"agent-planning-tools install: tools={','.join(tools)} target={target} "
        f"root={root}{' (dry run)' if dry_run else ''}")
    for dest, data, tool in plan_files(tools, target, prefix, explicit_prefix):
        digest = sha256(data)
        exists = os.path.lexists(dest)
        if exists and os.path.isdir(dest):
            raise InstallError(f"{dest} is a directory")
        if exists:
            with open(dest, "rb") as f:
                same = sha256(f.read()) == digest
            if same:
                out(f"UNCHANGED {dest}")
                planned += 1
                known.setdefault(dest, {"path": dest, "sha256": digest, "tool": tool})
                continue
            if not yes:
                out(f"SKIP      {dest} (exists and differs; use --yes to overwrite with a backup)")
                skipped += 1
                continue
            action = f"OVERWRITE {dest} (backup {dest}.bak-{stamp})"
        else:
            action = f"WRITE     {dest}"
        out(action)
        planned += 1
        if dry_run:
            continue
        for d in reversed(_missing_dirs(dest, root)):
            os.makedirs(d, exist_ok=True)
            dirs.append(d)
        if exists:
            os.replace(dest, f"{dest}.bak-{stamp}")
        with open(dest, "wb") as f:
            f.write(data)
        if dest.endswith(".py"):
            os.chmod(dest, 0o755)
        known[dest] = {"path": dest, "sha256": digest, "tool": tool}
    if not dry_run:
        for d in _missing_dirs(os.path.join(root, MANIFEST), root):
            os.makedirs(d, exist_ok=True)
            dirs.append(d)
        os.makedirs(root, exist_ok=True)
        with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
            json.dump({"files": list(known.values()),
                       "dirs": sorted(set(dirs))}, f, indent=2)
    out(f"manifest: {len(known) if not dry_run else planned} file(s) "
        f"{'planned' if dry_run else 'recorded'} under {root}")
    return 1 if skipped else 0


def uninstall(prefix, dry_run, yes, out=print):
    root = os.path.abspath(prefix)
    path = os.path.join(root, MANIFEST)
    if not os.path.exists(path):
        out(f"nothing to uninstall: no manifest at {path}")
        return 0
    manifest = load_manifest(root)
    out(f"agent-planning-tools uninstall: root={root}{' (dry run)' if dry_run else ''}")
    kept = 0
    for entry in manifest["files"]:
        dest = entry["path"]
        if not os.path.lexists(dest):
            out(f"MISSING   {dest}")
            continue
        with open(dest, "rb") as f:
            changed = sha256(f.read()) != entry.get("sha256")
        if changed and not yes:
            out(f"KEEP      {dest} (modified since install; use --yes to remove)")
            kept += 1
            continue
        out(f"REMOVE    {dest}")
        if not dry_run:
            os.remove(dest)
    if dry_run:
        return 0
    if kept:
        out("manifest kept: some files remain")
        return 1
    os.remove(path)
    for d in sorted(set(manifest["dirs"]), key=len, reverse=True):
        try:
            os.rmdir(d)
        except OSError:
            pass
    return 0


def choose_tools(arg, stdin=sys.stdin, out=print):
    if arg:
        return TOOLS if arg == "all" else (arg,)
    if stdin.isatty():
        answer = input("Install which tools? [metis/momus/all] ").strip().lower()
        if answer in TOOLS + ("all",):
            return TOOLS if answer == "all" else (answer,)
        raise InstallError(f"unknown choice {answer!r}")
    raise InstallError("--tools metis|momus|all is required when not run in a terminal")


def build_parser():
    p = argparse.ArgumentParser(prog="install.py",
                                description="Install agent-planning-tools (Metis and/or Momus).")
    p.add_argument("--tools", choices=("metis", "momus", "all"))
    p.add_argument("--target", choices=TARGETS, default="generic")
    p.add_argument("--prefix", metavar="DIR")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--yes", action="store_true")
    return p


def main(argv=None):
    if os.name == "nt":
        print("install.py: Windows is not supported", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    prefix = os.path.expanduser(args.prefix) if args.prefix else default_prefix(os.environ)
    try:
        if args.uninstall:
            return uninstall(prefix, args.dry_run, args.yes)
        tools = choose_tools(args.tools)
        return install(tools, args.target, prefix, bool(args.prefix),
                       args.dry_run, args.yes)
    except InstallError as exc:
        print(f"install.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"install.py: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
