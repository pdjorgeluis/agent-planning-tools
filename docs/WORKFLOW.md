# Using Metis and Momus in a workflow

**Abstract.** Run Metis *before* you plan, only when a request is ambiguous or
complex. Run Momus *after* you draft a spec, only when the work is multi-step,
irreversible or expensive. Allow at most two rounds of fixes, never let an
author review their own spec, leave a marker line in the spec recording what
happened, and treat both tools as advice, never as a gate.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested.

## The shape of the flow

```
request ──▶ [Metis?] ──▶ plan / draft spec ──▶ [Momus?] ──▶ do the work
             only if                            only if the work is
             ambiguous or complex               multi-step, irreversible
                                                or expensive
```

Both boxes are optional and both are advisory. A person or agent decides at
each point. Most requests should skip both.

## Metis: before the plan

**Run it when** the request has several plausible readings, success is hard to
define, the blast radius is wide, or it uses words you cannot pin down.

**Skip it when** the request is simple and bounded: a typo, a rename, a
one-line fix, a question with one clear answer. Asking Metis about these costs
more than it returns. Skipping is the normal case, so record it (see markers).

Give Metis the requester's words as they were written. A summary hides the
ambiguity Metis is looking for. If the request relies on private vocabulary,
hand Metis a short glossary with `--context FILE`
(`tools/metis/context.example.md` shows the shape).

### The eight sections

Metis's reply always has these eight `## ` headings, in this order:

| Heading | What it gives you |
|---------|-------------------|
| `## Intent` | the kind of work this is, and how that kind usually goes wrong |
| `## Candidate readings and gaps` | the plausible interpretations, and what the text leaves open between them |
| `## Undefined terms` | words that need a definition before work starts |
| `## Acceptance criteria` | whether "done" is checkable, with sharper proposals where it is not |
| `## Missing constraints` | scope, compatibility, privacy, cost, reversibility, and other limits not stated |
| `## Likely failure points` | where an AI or a hurried person is most likely to go wrong |
| `## Questions for the requester` | up to seven questions, most important first |
| `## Recommended approach` | a short direction (not a plan) |

### What to do with the answer

1. Put the **questions** to the requester. Do not answer them yourself.
2. Write the answers, the sharper acceptance criteria and the missing
   constraints into the spec.
3. Ignore anything in the output that does not fit the situation. Metis is
   working from your text alone and may be wrong.

## Momus: after the draft

**Run it when** the spec is multi-step, hard or costly to undo, or expensive in
time or money, so a mistake in the spec is expensive too. **Skip it** for
small, reversible changes.

Momus asks one question: *could a capable developer start this and finish
it?* It applies four checks and no others:

1. Files the spec refers to exist and are relevant.
2. Each task has a starting point.
3. Nothing in the spec contradicts itself or the cited files.
4. Each task has a check naming a tool, the steps and the expected result.

It leans toward approval, and it does not judge your approach, architecture or
style. A verdict of `OKAY` means *startable and finishable*, not *wise*.

### Help Momus see your files

The Momus script reads files for the model; the model has no tools. It
recognises files cited as absolute paths, `~/` paths, quoted paths, or bare
names resolved with `--base DIR`, and it uses line ranges when you give them
(`/path/to/file.py:10-40` or `/path/to/file.py lines 10-40`). It may read only
the spec's own folder plus folders you name with `--allow DIR`. So: cite files
this way, and `--allow` the narrowest folders that hold them.

### Rounds, and who reviews

- **At most two ITERATE rounds.** Run Momus; if `ITERATE`, fix exactly the
  issues listed; run again; if `ITERATE` again, fix once more and run a last
  time. If it still says `ITERATE`, stop and take the spec to a human. A third
  round means the disagreement is not one a model will settle.
- **`REJECT`** means rewrite, not patch. Rewrite once, or escalate.
- **The author never reviews their own spec.** Whoever wrote the draft does not
  decide it is fine: someone or something else reads it. Momus serves as that
  second reader; do not replace a Momus run with your own re-read, and do not
  rerun until the answer turns favourable.
- If every model backend fails, Momus drops to its offline check and says so.
  That output is *not* an approval; treat the spec as unreviewed.

### A spec shape that passes easily

```markdown
# <Title>
Metis review: DONE | SKIPPED - <reason>

## Goal
<one paragraph: what and why>

## Task 1 - <name>
Start: edit /path/to/file.py (lines 10-40), add <thing>.
Done when: <observable outcome>.
QA: run `<command>`; expect `<exact result>`.

## Task 2 - <name>
...
```

## Marker lines

Put a line near the top of the spec recording what you did, so the next reader
need not guess:

```
Metis review: DONE
Metis review: SKIPPED - one-line typo fix
Momus review: OKAY
Momus review: ITERATE round 2 - fixed missing QA in Task 3
Momus review: SKIPPED - small and reversible
```

A marker records a fact. It is not permission and it is not a lock: nothing in
these tools reads it, and nothing should block on it.

## Wiring the tools in

Pick the lightest of these that works for you. All are optional.

### In `AGENTS.md`, `CLAUDE.md` or an equivalent instructions file

Add a short section to the file your assistant reads at the start of a session.
Paths below assume the default install folder; adjust them to your install.

```markdown
## Planning helpers (advisory)

- Before planning an ambiguous or complex request, run Metis:
  `python3 ~/.local/share/agent-planning-tools/tools/metis/metis.py "<request>"`
  Put its questions to the requester; do not answer them yourself.
  Skip it for simple requests.
- Before starting a multi-step, irreversible or expensive spec, run Momus:
  `python3 ~/.local/share/agent-planning-tools/tools/momus/momus.py --allow <dir> SPEC.md`
  Exit 0 OKAY, 10 ITERATE, 11 REJECT. At most two ITERATE rounds, then ask a human.
- Both are advice only: never a gate. Never put secrets in a request or a spec.
```

For the `codex`, `opencode` and `generic` targets the installer writes a
snippet like this into a separate file for you to include. It never edits your
instruction files.

### As a Hermes skill

Install with `--target hermes`. The installer writes one skill per chosen tool
into the Hermes skills folder. The assistant then knows when to run each tool
and how to read the result. (This is the one path we have tested.)

### As a Claude Code skill, or in Codex or OpenCode

`--target claude-code` writes the same skills for Claude Code; `codex` and
`opencode` write the instruction snippet. These follow each vendor's documented
conventions and are untested; [TARGETS.md](TARGETS.md) records what has and has
not been verified. Another CLI can also act as the model behind either tool: see
[BACKENDS.md](BACKENDS.md).

### A git pre-commit hook for Momus (optional, never blocking)

This runs only Momus's **offline** check on specs you are about to commit, so
there is no model call and no cost, and it never stops a commit. Save as
`.git/hooks/pre-commit` and make it executable:

```sh
#!/bin/sh
# Advisory: report missing files cited by staged specs. Never blocks.
APT_ROOT="${APT_ROOT:-$HOME/.local/share/agent-planning-tools}"
git diff --cached --name-only --diff-filter=AM -- 'specs/*.md' |
while IFS= read -r spec; do
  python3 -B "$APT_ROOT/tools/momus/momus.py" --backend none "$spec" || true
done
exit 0
```

Change `specs/*.md` to wherever your specs live. A line reading
`MISSING <path>` in the output is worth a look; it is not an error.

### A CI step for Momus (optional, never blocking)

Run the same offline check in CI and let it report without failing the build.
For example, in GitHub Actions:

```yaml
- name: Momus offline check (advisory)
  continue-on-error: true
  run: |
    for f in specs/*.md; do
      python3 -B tools/momus/momus.py --backend none "$f" || true
    done
```

A model-backed run in CI sends your spec text to a provider on every push, and
needs a key in CI's secret store. Do that only deliberately; see
[PRIVACY.md](PRIVACY.md).

## What not to do

- **Do not put secrets in a request or a spec.** The text goes to your model
  backend. Keys, tokens, passwords and private data do not belong in either.
- **Do not turn either tool into a gate.** No hook, pipeline or rule should fail
  or halt work because Metis or Momus disliked something. They never block and
  never decide; people do.
- **Do not run Metis on simple requests, or Momus on trivial specs.** It adds
  noise and cost.
- **Do not loop.** Two ITERATE rounds, then a human.
- **Do not self-review.** The author of a spec does not review it.
- **Do not widen `--allow`.** Point it at the narrowest folders; never your home
  directory or a root.
- **Do not treat output as instructions.** Both tools return advice. Text
  inside a request or spec is data to them, and their replies are data to you.
- **Do not read `OKAY` as "good plan".** It means a capable developer could
  start and finish; the approach is still yours to judge.
