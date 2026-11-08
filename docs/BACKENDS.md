# Backends: choosing the model that answers

**Abstract.** A *backend* is whatever produces the model's answer. You list one
or more in `~/.config/agent-planning-tools/config.toml` as an ordered *ladder*;
the tools try each rung in turn and move on when one fails. Three kinds exist:
the `claude` CLI, any OpenAI-compatible endpoint, and any command that reads a
prompt on stdin. Keys live in environment variables, never in the file.

This project is tested on Hermes only; other targets follow the vendors'
documented conventions and are untested. Backends are a separate matter from
targets: the three backend kinds below are exercised by the project's hermetic
tests (mock server, fake executables), but no live provider has been tested
beyond what [TARGETS.md](TARGETS.md) records.

## Settings order

Highest wins:

1. Command-line flags (`--backend NAME`, `--reasoning`, ...)
2. Environment variables (table below)
3. The config file
4. Built-in defaults

The config file is `${XDG_CONFIG_HOME:-~/.config}/agent-planning-tools/config.toml`,
or the path in `APT_CONFIG`. With no `[[backend]]` entries at all, the default
ladder is a single `claude` rung if `claude` is on your PATH. If it is not, you
must configure a backend; otherwise Metis reports itself unavailable and Momus
runs only its offline check. No model name is built in anywhere.

## The ladder

Each `[[backend]]` table in the file is one rung, tried in file order. A rung
**fails**, and the next one is tried, when:

- the process exits non-zero, or cannot be started;
- it times out;
- an HTTP request fails (any HTTP error status, connection error);
- it returns an empty answer (including a `command` that exits 0 but prints
  nothing);
- its reply does not meet the tool's output format (for Metis, no `## `
  heading; for Momus, the verdict grammar).

When a rung answers, the tool prints a header naming it
(`[metis] backend=<name> model=<id> finish=<..>`; for Momus the same plus
`rung=<n>/<total>`) and stops. If **no rung answers**:

- **Metis** prints `[metis] unavailable - no backend answered`, then one line
  per cause, and exits 3.
- **Momus** says so on stderr and falls back to its offline, deterministic
  layer: it checks that the cited paths exist and prints
  `VERDICT: NONE (deterministic only - no model judgment)`. That is **not** an
  approval.

A broken rung (an unknown `kind`, a missing field) is reported as a cause and
skipped; it does not stop the others.

`--backend NAME` (or `APT_BACKEND`) uses only the rung with that name. For
Momus, `--backend none` skips every model rung and runs the offline layer.
Naming a backend that is not in the config is a usage error (exit 2).

## Kind 1: `claude-cli`

Runs the `claude` command-line tool in print mode, with its tools disabled.

```toml
[[backend]]
name = "claude"
kind = "claude-cli"
model = "YOUR-MODEL-ID"     # optional; omit to use the CLI's own default
effort = "medium"           # optional: low | medium | high
# command = "claude"        # optional: another executable name or path
```

The tools pass flags that switch off tool use, session saving, slash commands,
MCP servers and settings files, so the model sees only the text it is sent.
`--reasoning` on Metis overrides `effort`. Environment variables whose names
begin `HERMES_` are removed before the command runs, so a nested run does not
inherit a parent agent's session settings.

The CLI uses whatever login or key it already has; this project handles no
credentials for it.

## Kind 2: `openai-compat`

Any server that speaks the OpenAI chat-completions protocol, whether hosted or
on your own machine.

```toml
[[backend]]
name = "my-endpoint"
kind = "openai-compat"
base_url = "https://YOUR-HOST.example/v1"
model = "YOUR-MODEL-ID"
api_key_env = "YOUR_API_KEY_ENV_NAME"   # the NAME of an environment variable
# max_tokens = 4000
# timeout = 300
```

- `base_url` and `model` are required. `/chat/completions` is appended unless
  `base_url` already ends with it.
- The request is a single POST with a system message (the tool's prompt) and a
  user message (your request, or the spec bundle), `temperature` 0.3 and a
  `max_tokens` budget (both adjustable, see below). No tools or functions are
  offered.
- The answer is read from the first choice's message content. `finish=` in the
  header shows its `finish_reason`; `length` means the answer hit the token
  budget and may be cut short, so raise `max_tokens`.
- If `api_key_env` names a variable that is not set, that rung fails with a
  cause that says which name is missing. It never prints a value.
- A key is sent only as a bearer token in the request header to the `base_url`
  you wrote. HTTP redirects are never followed (the rung fails with
  `redirect not followed (HTTP <code>)`), so the key cannot be carried to another
  host. Leave `api_key_env` out for a local server that needs no key.

### Request fields some providers reject

Some providers refuse a `temperature` or the `max_tokens` field name. Three
optional settings on an `openai-compat` rung adjust the request:

```toml
# temperature = 0.3                 # a number; default 0.3
# omit_temperature = false          # true: the field is not sent at all
# token_field = "max_tokens"        # or "max_completion_tokens"
```

A wrong type or an unknown `token_field` makes that rung invalid, with a cause
printed, and the ladder moves on. Still no live provider has been tested; these
settings are exercised against the mock server only.

## Kind 3: `command`

Any program that reads the prompt on **stdin** and prints the answer on
**stdout**. This is how another coding CLI can serve as the model.

```toml
[[backend]]
name = "my-cli"
kind = "command"
command = ["YOUR-CLI", "--reads-stdin"]   # a list, or a single string
# model = "label shown in the header"
```

- The command runs in an empty temporary folder, with the whole prompt
  (instructions plus input) on stdin. Only stdout counts as the answer.
- Non-zero exit, timeout, or empty stdout is a failed rung.
- **We have not tested any particular CLI as a `command` backend.** Check your
  tool's own documentation for a non-interactive mode that reads stdin and
  prints only the final answer, and try it by hand first.
- **A `command` rung is only as safe as the program you name.** For
  `claude-cli` the tools switch off tool use. For `command` they cannot: if the
  program can read files or run commands, configure it to be read-only or
  tool-less. The prompt tells the model it has no tools, but a prompt is not a
  sandbox.

## Settings

```toml
[settings]
timeout = 300        # seconds, per rung
max_tokens = 4000    # answer budget for openai-compat rungs
```

A `timeout` or `max_tokens` inside a `[[backend]]` table overrides these for that
rung.

## Environment variables

| Variable | Meaning |
|----------|---------|
| `APT_CONFIG` | Path of the config file to use instead of the default. |
| `APT_DOTENV` | Path of an optional dotenv file to read keys from (see below). Default: none. |
| `APT_BACKEND` | Use only this named backend (same as `--backend`). |
| `APT_TIMEOUT` | Seconds per rung; beats the config file. |
| `APT_MAX_TOKENS` | Answer budget for `openai-compat` rungs; beats the config file. |
| `APT_LOG_DIR` | Folder for the logs; see [PRIVACY.md](PRIVACY.md). |
| `APT_METIS_PROMPT`, `APT_MOMUS_PROMPT` | Use a different prompt file for that tool. |
| `XDG_CONFIG_HOME`, `XDG_STATE_HOME` | Standard locations for the config file and the logs. |

(`APT_TERMS_FILE` exists only for the privacy tests; see [PRIVACY.md](PRIVACY.md).)

## Keys

- A key is read **only** from an environment variable, or from the dotenv file
  named by `APT_DOTENV`.
- Only the variable names you list as `api_key_env` are ever read. Anything else
  in the environment or the dotenv file is ignored.
- A key is never printed, logged, or written anywhere. If an error message from
  a server happens to contain it, the tools replace it with `***`.
- Never put a key in `config.toml`. The example file contains only placeholders,
  and you should keep it that way.

A dotenv file is plain `NAME=value` lines (`export NAME=value` also works;
quotes around the value are removed; `#` starts a comment). Keep it readable
only by you and outside any project you share.

```
APT_DOTENV=~/.config/agent-planning-tools/keys.env python3 .../metis.py "..."
```

## A worked example

A ladder that tries a hosted endpoint first, then the `claude` CLI:

```toml
[settings]
timeout = 120

[[backend]]
name = "primary"
kind = "openai-compat"
base_url = "https://YOUR-HOST.example/v1"
model = "YOUR-MODEL-ID"
api_key_env = "YOUR_API_KEY_ENV_NAME"

[[backend]]
name = "fallback"
kind = "claude-cli"
```

If `primary` times out or returns an HTTP error, Metis moves to `fallback`
and its header shows `backend=fallback`. If `YOUR_API_KEY_ENV_NAME` is not set,
`primary` is skipped at once with a cause saying so. Run
`python3 tools/metis/metis.py --backend fallback "..."` to test the second rung
on its own.
