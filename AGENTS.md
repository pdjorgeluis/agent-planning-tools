# AGENTS.md — working on agent-planning-tools

Instructions for AI agents and people who change this repository. (To
*install* the tools, see `docs/AGENT-INSTALL.md` instead.)

**Abstract.** This repo holds two advisory CLI tools, Metis and Momus, in pure
Python standard library. Keep it that way: no dependencies, hermetic tests, no
private data, no gates. Run `bash scripts/check.sh` before every commit; it must
print `ALL CHECKS PASSED`.

## Layout

- `lib/aptlib/` shared code: config, dotenv loader, backends ladder, log rotation.
- `tools/metis/`, `tools/momus/` one tool each: script, `prompt.md`, `SKILL.md`, tests.
- `install.py` installer; its tests are in `tests/`.
- `scripts/check.sh` runs every check; `scripts/privacy-scan.py` is the privacy gate.
- `docs/` guides. `docs/TARGETS.md` records what is verified per target.

## Rules

1. **Python 3.11+ standard library only.** No pip dependencies. Windows is
   unsupported and documented as such.
2. **Tests are hermetic.** `unittest` only. No network (use a local mock HTTP
   server), no real `claude` binary (use a fake executable in a temp dir), and no
   reads or writes of the real home directory: set `HOME` and the `XDG_*`
   variables to a temp dir. The one exemption is the file named by
   `APT_TERMS_FILE` (below).
3. **Advisory means advisory.** The tools never block, never decide, and write
   nothing but their own log. Do not add a mode that fails a build or stops
   work on a model's opinion.
4. **Models get no tools.** Only the Momus script reads files, inside allowed
   roots, never denied names. Do not weaken the deny list or add a path that
   hands a model a tool.
5. **Secrets stay out.** Keys come from environment variables or an optional
   dotenv file named by `APT_DOTENV`, are read only for names the config lists,
   and are never printed, logged, committed or put in test output.
6. **No private data in the repo.** No personal names, home paths, hostnames,
   addresses, chat ids or tokens. Examples use obvious fakes
   (`YOUR-MODEL-ID`, `YOUR_KEY_HERE`, `example.com`).
7. **Prompts are clean-room.** Write or revise `prompt.md` files from a plain
   role description. Never paste or paraphrase another project's prompt text.
   Credit inspirations in `NOTICE.md` only.
8. **Say what is tested.** Only Hermes is tested. Every user-facing document says
   "tested on Hermes only; other targets follow the vendors' documented
   conventions and are untested". Do not claim a target works until it has been
   run and recorded in `docs/TARGETS.md`.
9. **Do not publish.** No remote, no push and no release unless the maintainer
   says so.

## Checks

```
bash scripts/check.sh
```

runs the four test suites (`lib/aptlib/tests`, `tools/metis/tests`,
`tools/momus/tests`, `tests`), the privacy scan, an offline Momus run and an
installer round trip. To run one suite:

```
python3 -I -m unittest discover -s tools/momus/tests -t .
```

**Privacy gate.** The maintainer keeps a private terms file (one term per line)
outside this repository. Never store it here. Run:

```
APT_TERMS_FILE=/path/to/terms.txt bash scripts/check.sh
python3 scripts/privacy-scan.py --terms-file /path/to/terms.txt
```

The scan fails if any term, or anything that looks like a secret, an email, a
private address or a home path, appears in a file or in a commit's patch text.
Do not "fix" a finding by editing the scanner or its patterns; remove the
offending text.

## Style

- Plain, complete sentences in docs. Short paragraphs. Translate jargon on
  first use.
- Commits are small, on `main`, with conventional messages
  (`feat(momus): ...`, `docs: ...`, `fix(install): ...`).
- Keep prompt output formats in step with the parsers: Momus's verdict grammar
  is enforced in `tools/momus/momus.py`; Metis's eight `## ` headings are listed
  in `docs/WORKFLOW.md`. Change prompt and parser together, and update the tests.
- The Metis test that checks no glossary section is sent when `--context` is
  absent looks for the appended heading (`## Requester glossary`), so the
  prompt itself may use any wording.
