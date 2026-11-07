# agent-planning-tools

Two small, optional advisors for AI-assisted work, built with the Python
standard library only.

**Abstract.** *Metis* reads a request before anyone plans it and lists the
ambiguities, gaps and risks. *Momus* reads a drafted spec and says whether a
capable developer could start and finish it. Both are advisory: they never
block and never decide, and they write nothing but their own small log. You
choose at install time which of the two you want, and which model answers:
any OpenAI-compatible endpoint, the `claude` CLI, or any command-line tool
that reads a prompt on stdin.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested. See [docs/TARGETS.md](docs/TARGETS.md).

## What each tool does

| Tool | Reads | Answers | Output |
|------|-------|---------|--------|
| **Metis** | a request, before any plan exists | "What is unclear, risky or untestable here?" | Eight fixed `## ` sections ending in questions for the requester |
| **Momus** | a drafted spec plus excerpts of the files it cites | "Could a capable developer start this and finish it?" | `VERDICT: OKAY`, `ITERATE` or `REJECT`, a summary, up to three issues |

Metis is for **ambiguous or complex requests**; skip it for simple ones. Momus
is for specs that are **multi-step, irreversible or expensive**. Neither is a
gate: you decide what to do with what they say. Advice on weaving them into a
workflow is in [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Requirements

- A Unix-like system (developed and tested on Linux). Windows is not
  supported; the tools say so and exit rather than half-work.
- Python 3.11 or newer (the standard library's `tomllib` reads the config).
- One model backend (see below). Momus also runs without any model, in a
  limited deterministic mode.
- No packages to install. No network access except to the backend you
  configure.

## Quick start

```
git clone <URL of this repository> agent-planning-tools
cd agent-planning-tools
python3 install.py --tools all --target generic --dry-run   # see what it would write
python3 install.py --tools all --target generic             # do it
```

`--tools` takes `metis`, `momus` or `all`; leave it out in a terminal and the
installer asks. `--target` takes `hermes`, `claude-code`, `codex`, `opencode`
or `generic`. The installer copies only the tools you chose plus the shared
library, prints a manifest of every file it wrote, never overwrites a changed
file without `--yes` (and then keeps a `.bak-<timestamp>` copy), and can undo
itself with `--uninstall`. Full steps: [docs/INSTALL.md](docs/INSTALL.md). If an
AI agent is doing the installing, point it at
[docs/AGENT-INSTALL.md](docs/AGENT-INSTALL.md).

Then tell the tools which model to use. With the `claude` CLI on your PATH
there is nothing to configure. Otherwise copy `config.example.toml` to
`~/.config/agent-planning-tools/config.toml` and edit it
([docs/BACKENDS.md](docs/BACKENDS.md)). Keys go in environment variables,
never in the file.

Try them (paths are where the generic target puts files by default):

```
python3 ~/.local/share/agent-planning-tools/tools/metis/metis.py \
  "Add a way for users to export their data"

python3 ~/.local/share/agent-planning-tools/tools/momus/momus.py \
  --allow ~/projects/my-app  specs/export.md
```

Each prints a first line that tells you which backend answered, for example
`[metis] backend=claude model=n/a finish=n/a`, followed by the consultation or
the verdict.

No model yet? Momus still works offline:

```
python3 tools/momus/momus.py --backend none specs/export.md
```

This checks only that the files and line ranges the spec cites exist. It
prints `VERDICT: NONE (deterministic only - no model judgment)`, which is
**not** an approval.

## Exit codes

| | Metis | Momus |
|--|-------|-------|
| 0 | answered | OKAY (or deterministic check found no missing path) |
| 10 | n/a | ITERATE (or deterministic check found a missing path) |
| 11 | n/a | REJECT |
| 2 | bad input or configuration | bad input or configuration |
| 3 | unavailable: no backend answered | failure |

## Your data

The text you submit goes to the model backend you configure, and nowhere else.
Momus reads only the files the spec cites, only inside directories you allow,
never files that look like secrets, and gives the model no tools. Both tools
keep a small metadata-only log. Details, including what the log holds and the
limits of the safeguards, are in [docs/PRIVACY.md](docs/PRIVACY.md). Do not put
secrets in requests or specs.

## Documentation

| File | For |
|------|-----|
| [docs/INSTALL.md](docs/INSTALL.md) | people installing by hand |
| [docs/AGENT-INSTALL.md](docs/AGENT-INSTALL.md) | agents installing on a person's behalf |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | when to run each tool, and how to wire them in |
| [docs/BACKENDS.md](docs/BACKENDS.md) | choosing and configuring the model that answers |
| [docs/TARGETS.md](docs/TARGETS.md) | one section per supported CLI |
| [docs/PRIVACY.md](docs/PRIVACY.md) | what leaves your machine, what is logged |
| [AGENTS.md](AGENTS.md) | contributors and agents working on this repository |

## Repository layout

```
install.py              installer (tools, target, prefix, dry run, uninstall)
config.example.toml     example backend ladder: placeholders only
lib/aptlib/             shared code: config, dotenv loader, backends, log rotation
tools/metis/            metis.py, prompt.md, context.example.md, SKILL.md, tests
tools/momus/            momus.py, prompt.md, SKILL.md, tests
tests/                  installer and privacy-scanner tests
scripts/check.sh        runs every check
scripts/privacy-scan.py privacy gate for contributors
docs/                   the guides listed above
```

Run everything with `bash scripts/check.sh`; it prints `ALL CHECKS PASSED` on
success. The tests are hermetic: no network, no use of your real home
directory.

## Licence and credits

MIT. See [LICENSE](LICENSE). The two roles take their names and general idea
from other people's work; see [NOTICE.md](NOTICE.md). The prompts in this
repository were written from scratch.
