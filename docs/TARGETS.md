# Targets: where the installer puts things, and what is verified

**Abstract.** The installer supports four assistant CLIs plus a generic
fallback. **Tested on Hermes only; other targets follow the vendors' documented
conventions and are untested.** For each target this page says what the
installer writes, which vendor page backs the location, and which claims we
could not verify. "Verified in docs" means *the vendor's documentation said so
on 2026-11-07*; it never means we ran the tool on that CLI. Re-check the links:
vendors change their conventions.

| Target | Writes (home-relative) | Kind | Tested by us | Location checked in vendor docs |
|--------|------------------------|------|--------------|---------------------------------|
| `hermes` | `.hermes/skills/<tool>/SKILL.md` | skill | **yes** | by use |
| `claude-code` | `.claude/skills/<tool>/SKILL.md` | skill | untested | yes |
| `codex` | `.codex/agent-planning-tools.md` | snippet | untested | partly (see below) |
| `opencode` | `.config/opencode/agent-planning-tools.md` | snippet | untested | partly (see below) |
| `generic` | `agent-planning-tools-AGENTS.md` | snippet | untested | not applicable |

`<tool>` is `metis` or `momus`. The scripts themselves always go to
`~/.local/share/agent-planning-tools` (or `--prefix DIR`, in which case every
path above is under DIR). A *skill* is read by the assistant by itself; a
*snippet* is a file you copy lines from into your own instruction file. The
installer never edits an existing instruction file.

## Hermes (tested)

- Writes a skill per chosen tool to `~/.hermes/skills/<tool>/SKILL.md`.
- Tested: the installer and both tools were run on Hermes's host, including
  real model calls through the `claude` command (two calls per tool).
- Profiles: Hermes can keep skills per profile. The installer writes to the
  default location only; for a profile, copy the two skill files by hand into
  that profile's skills folder. This case is **untested**.
- Reference: <https://hermes-agent.nousresearch.com/docs>

## Claude Code (untested)

- Writes `~/.claude/skills/<tool>/SKILL.md`.
- Verified in docs (2026-11-07): personal skills live in
  `~/.claude/skills/<name>/SKILL.md`; a skill is a directory with a `SKILL.md`
  holding YAML frontmatter and instructions; Claude loads it when relevant or
  on `/<skill-name>`. <https://code.claude.com/docs/en/skills>
- Not verified: that our skill files' frontmatter is accepted unchanged by your
  Claude Code version. We did not run it there.

## Codex (untested)

- Writes `~/.codex/agent-planning-tools.md`, a snippet. **Codex does not load
  this file by itself.**
- Verified in docs (2026-11-07): Codex reads `AGENTS.md` from its home
  directory (`~/.codex`, or `$CODEX_HOME`; `AGENTS.override.md` wins if present)
  and from the project, walking from the repository root down.
  <https://developers.openai.com/codex/guides/agents-md>
- The working step is yours: copy the lines you want from the snippet into
  `~/.codex/AGENTS.md` or a project `AGENTS.md`. We did not verify any
  Codex-native skill mechanism, so none is shipped (not verified).
- Codex could also serve as the *model* through a `command` backend; the exact
  non-interactive invocation is not verified here. See [BACKENDS.md](BACKENDS.md).

## OpenCode (untested)

- Writes `~/.config/opencode/agent-planning-tools.md`, a snippet. **OpenCode
  does not load this file by itself.**
- Verified in docs (2026-11-07): global rules are read from
  `~/.config/opencode/AGENTS.md`, project rules from `AGENTS.md` (with
  `CLAUDE.md` as a fallback). <https://opencode.ai/docs/rules/>
- Verified in docs (2026-11-07): OpenCode also discovers skills in
  `~/.config/opencode/skills/` and, for compatibility, in `~/.claude/skills/`.
  <https://opencode.ai/docs/skills/> So a `claude-code` install may be seen by
  OpenCode too; the rules page documents `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS`
  to turn that off. We did not test this.
- Not verified: pointing OpenCode at the snippet through its configuration
  file. Copy the lines into `~/.config/opencode/AGENTS.md` instead.

## Generic

- Writes `~/agent-planning-tools-AGENTS.md` (or under `--prefix`): the same
  snippet, for any assistant that reads an `AGENTS.md`-style file. Copy the
  lines you want. Untested on every assistant.

## What "untested" costs you

If a target's convention has changed, the likely failure is quiet: the file
sits where the assistant never looks. The scripts do not depend on the target;
run them by hand as shown in [INSTALL.md](INSTALL.md) step 4 to confirm they
work, then fix the wiring.
