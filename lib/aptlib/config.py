"""Configuration: CLI flags > environment > config.toml > built-in defaults.

Keys (API tokens) are read ONLY from environment variables, or from an
optional dotenv file named by APT_DOTENV, and ONLY for the variable names the
config lists (``api_key_env``). They live in a private dict and are never
printed or logged.
"""

import os
import shlex
import shutil
import tomllib

KINDS = ("claude-cli", "openai-compat", "command")
DEFAULT_MAX_TOKENS = 4000
DEFAULT_TIMEOUT = 300


class ConfigError(Exception):
    """Fatal, user-facing configuration error (printed without traceback)."""


def config_path(env=None):
    env = os.environ if env is None else env
    explicit = env.get("APT_CONFIG")
    if explicit:
        return os.path.expanduser(explicit)
    home = os.path.expanduser("~")
    xdg = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return os.path.join(xdg, "agent-planning-tools", "config.toml")


def _positive_int(value, fallback):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if n > 0 else fallback


def parse_dotenv(text, wanted):
    """Return {name: value} for the names in ``wanted`` only."""
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if name not in wanted or name in found:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[name] = value
    return found


class Config:
    """Resolved settings for one run."""

    def __init__(self, rungs, invalid, max_tokens, timeout, log_dir, keys,
                 source):
        self.rungs = rungs          # list of validated rung dicts, in order
        self.invalid = invalid      # list of cause strings for broken rungs
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.log_dir = log_dir
        self._keys = keys           # private: {env name: value}
        self.source = source        # path of the config file used, or ""

    def key_for(self, rung):
        name = rung.get("api_key_env")
        return self._keys.get(name, "") if name else ""

    def secrets(self):
        """Values to redact from any error text."""
        return [v for v in self._keys.values() if v]


def _validate_rung(raw, index):
    """Return (rung, error). Never raises on a malformed rung."""
    if not isinstance(raw, dict):
        return None, f"backend #{index}: not a table"
    name = str(raw.get("name") or f"rung{index}")
    kind = raw.get("kind")
    if kind not in KINDS:
        return None, f"backend {name}: unknown kind {kind!r} (use {', '.join(KINDS)})"
    rung = {"name": name, "kind": kind}
    if "timeout" in raw:
        rung["timeout"] = _positive_int(raw["timeout"], 0) or None
    if kind == "claude-cli":
        rung["model"] = str(raw.get("model") or "")
        rung["effort"] = str(raw.get("effort") or "")
        rung["command"] = raw.get("command") or "claude"
    elif kind == "openai-compat":
        for need in ("base_url", "model"):
            if not raw.get(need):
                return None, f"backend {name}: missing {need}"
        rung["base_url"] = str(raw["base_url"])
        rung["model"] = str(raw["model"])
        rung["api_key_env"] = str(raw.get("api_key_env") or "")
        rung["max_tokens"] = _positive_int(raw.get("max_tokens"), 0) or None
    else:  # command
        if not raw.get("command"):
            return None, f"backend {name}: missing command"
        rung["command"] = raw["command"]
        rung["model"] = str(raw.get("model") or "")
    cmd = rung.get("command")
    if cmd is not None and not isinstance(cmd, (str, list)):
        return None, f"backend {name}: command must be a string or a list"
    return rung, None


def command_argv(command):
    """A configured command (string or list) as an argv list."""
    if isinstance(command, list):
        return [str(c) for c in command]
    return shlex.split(command)


def load(env=None, which=shutil.which):
    """Build the Config from the environment and the config file."""
    env = os.environ if env is None else env
    path = config_path(env)
    data, source = {}, ""
    if os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read config {path}: {exc}")
        source = path
    rungs, invalid = [], []
    raw_rungs = data.get("backend", [])
    if not isinstance(raw_rungs, list):
        raise ConfigError(f"config {path}: 'backend' must be an array of tables")
    for i, raw in enumerate(raw_rungs, 1):
        rung, err = _validate_rung(raw, i)
        if err:
            invalid.append(err)
        else:
            rungs.append(rung)
    if not raw_rungs and which("claude"):
        rungs.append({"name": "claude", "kind": "claude-cli", "model": "",
                      "effort": "", "command": "claude"})
    wanted = {r["api_key_env"] for r in rungs if r.get("api_key_env")}
    keys = {n: env[n] for n in wanted if env.get(n)}
    dotenv = env.get("APT_DOTENV")
    missing = wanted - set(keys)
    if dotenv and missing:
        try:
            with open(os.path.expanduser(dotenv), encoding="utf-8",
                      errors="replace") as f:
                for n, v in parse_dotenv(f.read(), missing).items():
                    if v:
                        keys[n] = v
        except OSError:
            pass
    section = data.get("settings", {}) if isinstance(data.get("settings"), dict) else {}
    max_tokens = _positive_int(env.get("APT_MAX_TOKENS") or section.get("max_tokens"),
                               DEFAULT_MAX_TOKENS)
    timeout = _positive_int(env.get("APT_TIMEOUT") or section.get("timeout"),
                            DEFAULT_TIMEOUT)
    log_dir = os.path.expanduser(env.get("APT_LOG_DIR") or os.path.join(
        env.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
        "agent-planning-tools"))
    return Config(rungs, invalid, max_tokens, timeout, log_dir, keys, source)


def select(cfg, name):
    """Narrow the ladder to one named rung. Returns the list (maybe empty)."""
    if not name:
        return list(cfg.rungs)
    return [r for r in cfg.rungs if r["name"] == name]
