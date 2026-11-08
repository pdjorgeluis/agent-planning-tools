# Installing agent-planning-tools (for people)

**Abstract.** Clone the repository, run `python3 install.py`, choose Metis,
Momus or both, and pick a target. The installer copies only what you chose,
shows you a manifest, and can undo itself. Afterwards, tell the tools which
model to use. The whole thing takes a few minutes and needs only Python 3.11 or
newer.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested. (If an AI agent is installing for you,
send it to [AGENT-INSTALL.md](AGENT-INSTALL.md).)

## Before you start

- **Python 3.11 or newer.** Check with `python3 --version`.
- **A Unix-like system.** Windows is not supported: the installer and both tools
  stop with a message instead of misbehaving.
- **A model to answer.** Any one of: the `claude` CLI on your PATH; an
  OpenAI-compatible chat endpoint (and its key); or another command-line tool
  that reads a prompt on stdin and prints the answer. See
  [BACKENDS.md](BACKENDS.md). You can install first and configure later; Momus
  also has an offline mode that needs no model.

## 1. Get the code

```
git clone https://github.com/pdjorgeluis/agent-planning-tools.git agent-planning-tools
cd agent-planning-tools
```

(Or download and unpack an archive, then `cd` into it.) You run the installer
from this folder. The folder can be deleted afterwards; the installed copy is
self-contained.

## 2. Preview, then install

See what would be written, without writing anything:

```
python3 install.py --tools all --target generic --dry-run
```

Then install:

```
python3 install.py --tools all --target generic
```

The options:

| Option | Meaning |
|--------|---------|
| `--tools metis`, `momus` or `all` | Which tool to install. In a terminal, leaving it out makes the installer ask; with no terminal (a script, CI) it is required. |
| `--target NAME` | Which assistant to prepare: `hermes`, `claude-code`, `codex`, `opencode` or `generic` (default). |
| `--prefix DIR` | Install under DIR instead of the default. DIR is created if it does not exist. |
| `--dry-run` | Print what would happen; write nothing. |
| `--yes` | Allow overwriting a file that exists and differs, after backing it up. |
| `--uninstall` | Remove what a previous install recorded. |

Without `--prefix`, the tools go to `$XDG_DATA_HOME/agent-planning-tools`, which
is `~/.local/share/agent-planning-tools` unless you have set `XDG_DATA_HOME`.
With `--prefix`, the target's own file (below) is written under the prefix too,
which makes a trial install easy to throw away.

### What gets written

- The shared library (`lib/aptlib/`), `LICENSE`, `NOTICE.md` and
  `config.example.toml`.
- For each tool you chose: its script, `prompt.md`, `SKILL.md` and (Metis only)
  `context.example.md`. A tool you did not choose is not copied.
- One target file per the table below.
- `.apt-manifest.json`, the list of everything the installer wrote. Uninstall
  uses it.

The installer prints one line per file (`WRITE`, `UNCHANGED`, `SKIP` or
`OVERWRITE`) and a manifest count at the end.

### Targets

| Target | Writes | Kind |
|--------|--------|------|
| `hermes` | `~/.hermes/skills/apt-<tool>/SKILL.md` | a skill, one per tool |
| `claude-code` | `~/.claude/skills/apt-<tool>/SKILL.md` | a skill, one per tool |
| `codex` | `~/.codex/agent-planning-tools.md` | a snippet for you to include |
| `opencode` | `~/.config/opencode/agent-planning-tools.md` | a snippet for you to include |
| `generic` | `agent-planning-tools-AGENTS.md` in your home directory | a snippet for you to include |

With `--prefix DIR`, replace `~` with DIR. Skill files name the install path
inside them, so the assistant knows where the scripts are.

**Only Hermes has been tested.** The other locations follow each vendor's
documented conventions as we understand them, and are untested; what has been
checked against vendor documentation, and what has not, is recorded in
[TARGETS.md](TARGETS.md). Snippet targets are never edited into your existing
instruction files: you copy the lines you want into your own `AGENTS.md` or
equivalent. See [WORKFLOW.md](WORKFLOW.md) for how.

## 3. Choose a model

If `claude` is on your PATH and you configure nothing, a single `claude` backend
is used. Otherwise:

```
mkdir -p ~/.config/agent-planning-tools
cp config.example.toml ~/.config/agent-planning-tools/config.toml
```

Edit the copy: replace every `YOUR-...` placeholder. **Never write an API key
into the file.** Put the key in an environment variable and write only the
variable's *name* in `api_key_env`. Details: [BACKENDS.md](BACKENDS.md).

## 4. Check that it works

Let `ROOT` be your install folder (the default is shown):

```
ROOT=~/.local/share/agent-planning-tools

# Offline, no model, no cost: should print a [momus] header and exit 0 or 10.
python3 "$ROOT/tools/momus/momus.py" --backend none README.md

# Uses your model (one small call): should print a [metis] header, then sections.
python3 "$ROOT/tools/metis/metis.py" "Add a way for users to export their data"
```

(Run the first from a folder that contains a `README.md`, or give it any
`.md` file.) If Metis prints `[metis] unavailable` followed by causes, your
model is not configured yet; the causes say why.

## Installing twice, upgrading

Running the installer again is safe. Identical files are reported
`UNCHANGED`. A file that differs is **skipped** (and the installer exits 1)
unless you pass `--yes`, in which case the old file is first moved to
`<file>.bak-<timestamp>`. Upgrade by updating your clone, then running the
installer again with `--yes`.

## Uninstalling

```
python3 install.py --uninstall                 # or add --prefix DIR if you used one
```

Only files recorded in the manifest are removed, and a file you edited since
install is kept (with a note) unless you add `--yes`. Directories the installer
created are removed if they are empty. Your config file, your logs and any
`.bak-` copies are never touched. Python's bytecode caches (`__pycache__`) are
not in the manifest: if you ran the tools without `python3 -B`, delete those
folders by hand, or delete the install folder.

## Troubleshooting

| Symptom | Likely cause and fix |
|---------|----------------------|
| `--tools metis\|momus\|all is required when not run in a terminal` | Give `--tools` explicitly. |
| `SKIP ... exists and differs` and exit 1 | An older or edited copy is in place. Look at it, then re-run with `--yes` if you want it replaced (a backup is kept). |
| `Windows is not supported` | Use a Unix-like system, or WSL. |
| `[metis] unavailable` | No backend answered. Read the causes beneath it; see [BACKENDS.md](BACKENDS.md). |
| `[momus] no backend configured; deterministic layer only` | No model configured. Momus still ran its offline checks; that is not an approval. |
| Python errors mentioning `tomllib` | Python is older than 3.11. |

Logs live in `${XDG_STATE_HOME:-~/.local/state}/agent-planning-tools/`; see
[PRIVACY.md](PRIVACY.md).
