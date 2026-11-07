# Privacy: what leaves your machine, and what is kept

**Abstract.** The text you give Metis or Momus, plus (for Momus) excerpts of
the files the spec cites, is sent to the model backend you configured, and to
nobody else. Momus reads only inside folders you allow, refuses files that look
like secrets, and gives the model no tools. Both tools write one small
metadata log and nothing else. The safeguards are name-based and have limits,
listed below: keep secrets out of requests, specs and the folders you allow.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested.

## What leaves your machine

| Backend kind | What is sent, and to whom |
|--------------|---------------------------|
| `openai-compat` | The tool's prompt plus your request (Metis) or the spec bundle (Momus), in one HTTPS or HTTP request to the `base_url` you wrote. A key, if configured, goes in that request's header. |
| `claude-cli` | The same text, to the `claude` program, which sends it to its own service under its own terms. |
| `command` | The same text, on stdin, to the program you named. What that program does next is up to it. |
| Momus `--backend none` | **Nothing.** No model is called. |

There is no telemetry, no update check and no other network traffic from this
project. The installer and the tools contact nothing but the backend you chose.

**For Metis** the payload is your request, your optional `--context` glossary
(first 20000 characters) and the fixed prompt.

**For Momus** the payload is the spec **in full**, plus for each cited file an
excerpt: the lines you cited with five lines of context either side, or the
first 80 lines when no range was cited. A file over 5 MB is read only up to
5 MB.

Check your provider's own data policy: whether it stores prompts, trains on
them or logs them is outside this project's control.

## What Momus will not read

Only the Momus script reads files (the model has no tools). It reads a file
only if **all** of these hold:

- It is inside the spec's own folder or a folder you named with `--allow` or
  `--base`.
- No part of the path, as written or after following symlinks, matches the deny
  list: `.env`, `*.env`, `.env.*`, `*token*`, `*secret*`, `*credential*`,
  `auth.json`, `id_rsa*`, `id_ed25519*`; or lies under `~/.ssh` or `~/.gnupg`.
- It does not escape the allowed folders with `..` or through a symlink.

Matching is case-insensitive and applies to every component of the path, so
`notes/secrets-draft.md` and `tokens/readme.md` are refused. The rule **fails
closed**: if there is doubt, the file is not read. A refused file appears to
the model as `=== DENIED <path> (<reason>) ===`: its path and the reason, never
its content. Denied content does not reach the model, stdout or the log.

### Limits you should know

- The deny list is by **name and location**, not content. A secret pasted into
  an innocently named file inside an allowed folder *will* be sent. Allow the
  narrowest folders that hold the files your spec cites, and never your home
  directory or a filesystem root.
- Momus does **not** scan the spec, or files, for secrets before sending. Do
  not write secrets in a spec.
- The safeguards assume a Unix-like filesystem. Windows paths are unsupported,
  and the tools refuse to run there.
- A `command` backend is trusted with whatever you send it, and may be able to
  act on it. See [BACKENDS.md](BACKENDS.md).

## Prompt injection

Text in a request, a spec or a cited file may try to instruct the model ("ignore
your rules", "approve this"). Both prompts tell the model to treat all such text
as data, and Momus's parser accepts only its fixed verdict format, so a reply
that wanders off-format is rejected and the next rung is tried. A prompt is not
a guarantee. That is one more reason both tools are advisory and neither can
act on anything: they cannot change a file, run a command or send a message on
their own. Treat what they return as data, too.

## What they write

Neither tool writes anything except its own log. They do not modify your specs,
your requests or your source.

Logs live in `${XDG_STATE_HOME:-~/.local/state}/agent-planning-tools/`, or in
`APT_LOG_DIR` if set (the folder is created private to you):

- `metis-reviews.md` — one entry per call: time, the first **100 characters** of
  the request (whitespace collapsed), backend, model, outcome.
- `momus-reviews.md` — one entry per call: time, the spec's **absolute path** and
  the **SHA-256 hash** of its bytes, backend, verdict, issue count. It does
  **not** store the spec's text or any file excerpt.

Neither log ever holds a key, a full request, or file contents. At 50 entries a
log rolls over into `<tool>-reviews-archive-YYYY-MM.md` in the same folder. The
logs are plain text; delete them whenever you like. If the folder is not
writable, the tool prints a warning on stderr and carries on: a logging problem
never fails a review.

Note what the log does reveal: part of each Metis request (100 characters) and
the path of each spec. If even that is sensitive, point `APT_LOG_DIR` at a
temporary folder.

## Keys

Keys are read from environment variables, or from the dotenv file named by
`APT_DOTENV`, and only for the names listed as `api_key_env`. They are held in
memory for the run, never printed or logged, and removed from error text. See
[BACKENDS.md](BACKENDS.md#keys).

## For contributors: the privacy gate

This repository must never contain private data. `scripts/privacy-scan.py`
enforces that:

```
python3 scripts/privacy-scan.py --terms-file /path/to/terms.txt
```

It fails with exit status 1 if any of these appears in any tracked or untracked
non-ignored file, or in the patch text of any commit (commit headers are not
scanned):

- any term from the terms file (one per line, case-insensitive);
- a private-key header; a secret-key, GitHub-token or Slack-token prefix; a
  long token next to a word such as `key`, `token`, `secret` or `password`;
- a home-directory path, an email address, a private (RFC 1918) IPv4 address, or
  an identifier of 8 to 10 digits.

Findings print as `file:line: kind`; the matched text is never echoed.

The terms file lists the names, paths and identifiers of whoever maintains the
repository. It is supplied by the maintainer and **must never be stored in
this repository**. Without `--terms-file` only the pattern checks run. Tests
that need the terms read the file named by the `APT_TERMS_FILE` environment
variable and are skipped when it is not set; that is the only place the
test suite touches anything outside its own temporary folders.

The scanner's own source and tests assemble every forbidden pattern from
fragments at run time, so that scanning the repository passes without an
allowlist. If the gate flags text, remove the text; do not weaken the scanner.
