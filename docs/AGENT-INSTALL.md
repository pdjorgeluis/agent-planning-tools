# Installing agent-planning-tools (for agents)

**Abstract.** You are an AI agent installing Metis and/or Momus for a person.
Follow the numbered steps in order. Every step ends with a **Verify** command and
the result you must see before moving on. If a result differs, stop and report
it; do not improvise. Never write, print or ask to be told an API key.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested. Say so to the person when you report.

## Ground rules

- Ask the person; do not guess. You need three answers (step 2).
- Install only what they chose. Do not add tools, targets or backends they did
  not ask for.
- Do not use `--yes` unless the person has agreed to overwrite a differing
  file. `--yes` backs the old file up as `<file>.bak-<timestamp>` first.
- Do not edit the person's existing instruction files (`AGENTS.md`,
  `CLAUDE.md` or others). The installer never does either; show the person the
  snippet and let them decide.
- Do not run the live model check in step 8 without the person's agreement: it
  sends text to their model provider and may cost money.
- Windows is not supported. Stop if you are on Windows.
- Run the installed tools with `python3 -B`, as the steps below do. Without it
  Python leaves `__pycache__` files in the install folder; they are not in the
  manifest, so uninstall would not remove them.

## Steps

### 1. Check the environment

```
python3 -c "import sys; print(sys.version_info >= (3, 11))"
```

**Verify:** prints `True`. If `False` or the command is missing, stop: Python
3.11 or newer is required.

### 2. Ask the person three questions

1. Which tools: `metis`, `momus` or `all`?
2. Which target: `hermes`, `claude-code`, `codex`, `opencode` or `generic`?
3. Install under the default folder (`~/.local/share/agent-planning-tools`) or
   a `--prefix DIR` of their choice?

Remember: only `hermes` has been tested. Tell them if they pick another target.

**Verify:** you hold three explicit answers. Set shell variables for the
rest (replace the values):

```
TOOLS=all; TARGET=generic; ROOT="$HOME/.local/share/agent-planning-tools"
```

If they chose a prefix, set `ROOT` to it and add `--prefix "$ROOT"` to the
installer commands below (the examples show it as `PFX`):

```
PFX=""            # or: PFX="--prefix $ROOT"
```

### 3. Be in the repository

```
cd /path/to/agent-planning-tools && test -f install.py && test -d tools/metis && echo REPO-OK
```

**Verify:** prints `REPO-OK`. If the repository is not on disk, get it from the
URL the person gives you, then repeat this step.

### 4. Dry run

```
python3 install.py --tools "$TOOLS" --target "$TARGET" $PFX --dry-run; echo "exit=$?"
```

**Verify:** `exit=0`; every line starts with `WRITE`, `UNCHANGED` or
`OVERWRITE` (never `SKIP`); the last line begins `manifest:`. With
`--tools metis` no path contains `momus`, and with `--tools momus` none contains
`metis`. If you see `SKIP` lines or `exit=1`, a differing file is already
there: show the person the paths, and continue only if they approve `--yes`.

### 5. Install

```
python3 install.py --tools "$TOOLS" --target "$TARGET" $PFX; echo "exit=$?"
```

Add `--yes` only if the person approved overwriting in step 4.

**Verify:** `exit=0`, and the manifest file exists:

```
test -f "$ROOT/.apt-manifest.json" && echo MANIFEST-OK
```

prints `MANIFEST-OK`. Keep the printed list of files: you will report it.

### 6. Check the installed tools run, offline

```
cd "$(mktemp -d)" && printf 'A spec that cites no files.\n' > spec.md
python3 -B "$ROOT/tools/momus/momus.py" --backend none spec.md; echo "exit=$?"
```

(Only if Momus was installed.)

**Verify:** the first line begins `[momus] backend=none model=none finish=n/a`,
the second reads `VERDICT: NONE (deterministic only - no model judgment)`, and
`exit=0`. This shows that the installed files run; it says nothing about
whether a model answers. (It writes one metadata line to the Momus log; see
[PRIVACY.md](PRIVACY.md).)

For Metis, with no model call:

```
python3 -B "$ROOT/tools/metis/metis.py" --help | head -1; echo "exit=$?"
```

**Verify:** the first line begins `usage: metis.py`.

### 7. Configure a model, with the person

Run `command -v claude`. If it prints a path and the person wants to use it, no
configuration is needed. Otherwise help them create
`~/.config/agent-planning-tools/config.toml` from `config.example.toml`
(copy it into place, then replace each `YOUR-...` value with what the person
tells you). See [BACKENDS.md](BACKENDS.md).

For an endpoint that needs a key: write only the **name** of the environment
variable in `api_key_env`, and ask the person to set that variable themselves.
Do not ask for the key, do not paste it anywhere and do not echo it.

**Verify (names only, no values):**

```
test -f "$HOME/.config/agent-planning-tools/config.toml" && echo CONFIG-OK
python3 -c "import os,sys; print('KEY-SET' if os.environ.get(sys.argv[1]) else 'KEY-MISSING')" THE_ENV_VAR_NAME
```

The first prints `CONFIG-OK` (skip it if `claude` is the only backend); the
second prints `KEY-SET` for the variable name you wrote in the config (skip it
for backends without a key).

### 8. Check a model answers (with the person's agreement)

```
python3 -B "$ROOT/tools/metis/metis.py" "Add a way for users to export their data" | head -3; echo "exit=${PIPESTATUS[0]}"
```

(Use bash. Skip if Metis was not installed; for Momus alone, run
`momus.py` on a small real spec without `--backend none` and expect a `VERDICT:`
line.)

**Verify:** the first line begins `[metis] backend=` and the output continues with
a `## Intent` heading; `exit=0`. If it prints `[metis] unavailable`, read the
causes under it, fix the configuration with the person, and repeat. Do not claim
success until this passes, or the person tells you to leave the model for later.

### 9. Check the target file

Find the file the installer wrote for the target in the manifest output
(step 5), then confirm it exists and names the install folder:

```
grep -c "$ROOT" PATH_TO_THE_TARGET_FILE
```

**Verify:** the count is 1 or more. (For `hermes` and `claude-code` the file is a
`SKILL.md` per tool; for `codex`, `opencode` and `generic` it is a snippet file
for the person to include in their own instructions. Do not include it
yourself.)

### 10. Report

Tell the person, in plain terms: what you installed and where; the manifest
file list; which of steps 6 to 9 passed, and which you skipped; and that only
Hermes has been tested, so their target is untested. Mention how to undo it
(below). Do not report a skipped check as passed.

## Undoing the install

```
python3 install.py --uninstall $PFX; echo "exit=$?"
```

**Verify:** `exit=0` and the manifest file is gone
(`test ! -f "$ROOT/.apt-manifest.json" && echo GONE`). Only files recorded in the
manifest are removed; edited files are kept unless `--yes` is given.

## If something fails

Stop and report the exact command, its exit status and its output. Do not retry
with `--yes`, do not delete files by hand, and do not edit the repository to make
a check pass.
