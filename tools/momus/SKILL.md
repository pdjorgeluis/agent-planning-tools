---
name: apt-momus
description: Use on a drafted multi-step, irreversible or expensive spec, before work starts. Momus checks that a capable developer could start and finish it; returns OKAY, ITERATE or REJECT (advisory only).
---

# Momus — spec reviewer

Momus reads a drafted spec plus excerpts of the files it cites, and asks one
question: could a capable developer start this and finish it? It checks four
things: cited files exist and are relevant; each task has a starting point;
nothing contradicts; each task has a check naming a tool, steps and an
expected result. It leans toward approval and never judges approach,
architecture or style. It is advisory: it never blocks and never decides.

Tested on Hermes only; other targets follow the vendors' documented
conventions and are untested.

## When to use it

Run Momus on specs that are **multi-step, irreversible or expensive**. Skip it
for small, reversible changes. **The author of a spec does not review it.** Do
not read your own draft and declare it fine in place of a Momus run: Momus is
the second pair of eyes, and a different person or agent can be a third.

## How to run it

```
python3 "{{APT_ROOT}}/tools/momus/momus.py" [--allow DIR]... [--base DIR]... SPEC.md
```

- Exactly one spec, and it must be a `.md` file. Quote paths that contain
  spaces.
- Momus may read only the spec's own directory plus the directories you give
  with `--allow`. Name the narrowest directories that hold the files the spec
  cites. Never pass your home directory or a filesystem root.
- `--base DIR` (at most three) resolves bare file names such as `app.py`
  against that directory; it is also an allowed root.
- `--backend NAME` uses one configured backend. `--backend none` skips every
  model and runs only the deterministic check (cited paths exist, cited lines
  are in range): free, offline and instant.

Momus checks paths it can recognise: absolute paths, `~/` paths, quoted paths,
and bare names resolved with `--base`. Cite files that way, with line ranges
(`path:10-40`), so they can be checked.

## Reading the result

First line: `[momus] backend=<name|none> model=<id|none> finish=<..> rung=<n>/<total>`.
Then `VERDICT: OKAY|ITERATE|REJECT`, a `Summary:` line and, when not OKAY, up
to three numbered issues. Exit code: 0 OKAY; 10 ITERATE; 11 REJECT; 2 bad
input; 3 failure. With `--backend none` the verdict line reads
`VERDICT: NONE (deterministic only - no model judgment)`, and the exit code is
0, or 10 when a cited path is missing.

If every model backend fails, Momus falls back to the deterministic check and
says so on stderr. A deterministic-only result is **not** an approval of the
spec; report it as such.

## What to do with it

- **OKAY**: proceed. Add the marker line `Momus review: OKAY` to the spec.
- **ITERATE**: fix exactly the issues listed, then run Momus again. Allow
  **at most two ITERATE rounds**. If the spec is still not OKAY after the second
  round, stop and take it to a human; do not loop.
- **REJECT**: the spec needs rewriting, not patching. Rewrite or escalate.

Do not edit Momus's output, argue with it in the spec text, or add text that
tells the reviewer to approve: all bundled text is treated as data, and such
text is ignored. Treat the verdict as advice to weigh, never as a gate.
