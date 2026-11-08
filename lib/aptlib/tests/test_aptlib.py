import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "lib"))

from aptlib import backends, config, logs, testkit  # noqa: E402
from aptlib.testkit import Sandbox, put, make_fake, make_sleeper, ok_body  # noqa: E402


class ConfigTests(Sandbox):
    def load(self, **extra):
        return config.load(self.env(**extra), which=lambda n: None)

    def test_no_config_no_claude_means_no_rungs(self):
        cfg = self.load()
        self.assertEqual(cfg.rungs, [])

    def test_default_ladder_is_claude_when_on_path(self):
        cfg = config.load(self.env(), which=lambda n: "/x/claude" if n == "claude" else None)
        self.assertEqual([r["kind"] for r in cfg.rungs], ["claude-cli"])
        self.assertEqual(cfg.rungs[0]["model"], "")  # no vendor model hardcoded

    def test_config_file_ladder_in_order(self):
        self.write_config(self.server_config("http://h/v1", "a") +
                          '[[backend]]\nname="b"\nkind="command"\ncommand="cat"\n')
        cfg = self.load()
        self.assertEqual([r["name"] for r in cfg.rungs], ["a", "b"])

    def test_missing_fields_become_causes_not_crashes(self):
        self.write_config('[[backend]]\nname="x"\nkind="openai-compat"\nmodel="m"\n'
                          '[[backend]]\nname="y"\nkind="nope"\n'
                          '[[backend]]\nname="z"\nkind="command"\n')
        cfg = self.load()
        self.assertEqual(cfg.rungs, [])
        self.assertEqual(len(cfg.invalid), 3)
        self.assertIn("missing base_url", cfg.invalid[0])

    def test_bad_toml_raises_config_error(self):
        self.write_config("[[backend\n")
        with self.assertRaises(config.ConfigError):
            self.load()

    def test_apt_config_overrides_path(self):
        p = os.path.join(self.dir, "alt.toml")
        with open(p, "w") as f:
            f.write(self.server_config("http://h/v1", "alt"))
        self.assertEqual(self.load(APT_CONFIG=p).rungs[0]["name"], "alt")

    def test_env_beats_file_for_settings(self):
        self.write_config("[settings]\ntimeout = 11\nmax_tokens = 22\n")
        cfg = self.load(APT_TIMEOUT="33")
        self.assertEqual((cfg.timeout, cfg.max_tokens), (33, 22))

    def test_settings_defaults(self):
        cfg = self.load()
        self.assertEqual((cfg.timeout, cfg.max_tokens), (300, 4000))

    def test_log_dir_xdg_and_override(self):
        self.assertTrue(self.load().log_dir == self.logs)
        env = self.env()
        del env["APT_LOG_DIR"]
        cfg = config.load(env, which=lambda n: None)
        self.assertEqual(cfg.log_dir, os.path.join(self.home, ".state", "agent-planning-tools"))

    def test_key_from_env(self):
        self.write_config(self.server_config("http://h/v1", "a", key_env="MY_KEY"))
        cfg = self.load(MY_KEY="abcd1234")
        self.assertEqual(cfg.key_for(cfg.rungs[0]), "abcd1234")

    def test_dotenv_only_listed_names_loaded(self):
        self.write_config(self.server_config("http://h/v1", "a", key_env="MY_KEY"))
        dot = os.path.join(self.dir, "dot")
        with open(dot, "w") as f:
            f.write("export MY_KEY='fromdot1'\nOTHER_SECRET=nope\n")
        cfg = self.load(APT_DOTENV=dot)
        self.assertEqual(cfg.key_for(cfg.rungs[0]), "fromdot1")
        self.assertEqual(cfg.secrets(), ["fromdot1"])  # OTHER_SECRET never loaded

    def test_env_wins_over_dotenv(self):
        self.write_config(self.server_config("http://h/v1", "a", key_env="MY_KEY"))
        dot = os.path.join(self.dir, "dot")
        with open(dot, "w") as f:
            f.write("MY_KEY=fromdot1\n")
        cfg = self.load(APT_DOTENV=dot, MY_KEY="fromenv1")
        self.assertEqual(cfg.key_for(cfg.rungs[0]), "fromenv1")

    def test_select_by_name(self):
        self.write_config(self.server_config("http://h/v1", "a") + self.server_config("http://h/v1", "b"))
        cfg = self.load()
        self.assertEqual([r["name"] for r in config.select(cfg, "b")], ["b"])
        self.assertEqual(config.select(cfg, "zzz"), [])

    def test_parse_dotenv_quotes_and_comments(self):
        got = config.parse_dotenv('# c\nA="x y"\nB=2\n\nC', {"A", "B"})
        self.assertEqual(got, {"A": "x y", "B": "2"})


class BackendTests(Sandbox):
    def cfg(self, text, **extra):
        self.write_config(text)
        return config.load(self.env(**extra), which=lambda n: None)

    def test_openai_compat_success_and_auth_header(self):
        srv = self.server((200, ok_body("hello")))
        cfg = self.cfg(self.server_config(srv.base_url, "m", key_env="K1"), K1="tok-12345")
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "sys", "usr")
        self.assertEqual((reply.text, reply.finish, reply.name, causes), ("hello", "stop", "m", []))
        self.assertEqual(srv.requests[0]["auth"], "Bearer tok-12345")
        self.assertTrue(srv.requests[0]["path"].endswith("/chat/completions"))

    def _redirect_case(self, code, location=None):
        target = self.server((200, ok_body("stolen")))
        loc = location or (target.base_url + "/chat/completions")
        first = self.server((code, b"moved", {"Location": loc}))
        cfg = self.cfg(self.server_config(first.base_url, "m", key_env="K1"),
                       K1="tok-12345")
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "sys", "usr")
        self.assertIsNone(reply)
        self.assertEqual(target.requests, [])
        self.assertIn(f"redirect not followed (HTTP {code})", causes[0])
        self.assertNotIn("tok-12345", " ".join(causes))
        return target, first

    def test_redirect_301_not_followed_key_never_forwarded(self):
        target, first = self._redirect_case(301)
        self.assertEqual(len(first.requests), 1)
        self.assertEqual(target.requests, [])

    def test_redirect_302_not_followed(self):
        self._redirect_case(302)

    def test_redirect_303_not_followed(self):
        self._redirect_case(303)

    def test_redirect_307_still_an_error(self):
        self._redirect_case(307)

    def test_relative_redirect_not_followed_and_ladder_continues(self):
        first = self.server((302, b"x", {"Location": "/elsewhere"}))
        second = self.server((200, ok_body("fine")))
        cfg = self.cfg(self.server_config(first.base_url, "a", key_env="K1") +
                       self.server_config(second.base_url, "b"), K1="tok-12345")
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertEqual(reply.text, "fine")
        self.assertEqual(len(first.requests), 1)
        self.assertIn("redirect not followed (HTTP 302)", causes[0])

    def _sent(self, extra_toml):
        srv = self.server((200, ok_body("hi")))
        cfg = self.cfg(self.server_config(srv.base_url, "m") + extra_toml)
        reply, _ = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertEqual(reply.text, "hi")
        return json.loads(srv.requests[0]["raw"])

    def test_temperature_default_sent(self):
        p = self._sent("")
        self.assertEqual(p["temperature"], 0.3)
        self.assertEqual(p["max_tokens"], 4000)
        self.assertNotIn("max_completion_tokens", p)

    def test_temperature_custom_sent(self):
        self.assertEqual(self._sent("temperature = 1\n")["temperature"], 1)

    def test_omit_temperature_not_sent(self):
        self.assertNotIn("temperature", self._sent("omit_temperature = true\n"))

    def test_token_field_max_completion_tokens(self):
        p = self._sent('token_field = "max_completion_tokens"\n')
        self.assertEqual(p["max_completion_tokens"], 4000)
        self.assertNotIn("max_tokens", p)

    def test_bad_temperature_marks_rung_invalid(self):
        for bad in ('temperature = "hot"', "temperature = true", "temperature = nan",
                    "omit_temperature = 1", 'token_field = "max_tokenz"'):
            cfg = self.cfg(self.server_config("http://h/v1", "bad") + bad + "\n")
            self.assertEqual(cfg.rungs, [], bad)
            self.assertEqual(len(cfg.invalid), 1, bad)
            self.assertIn("backend bad:", cfg.invalid[0])

    def _env_probe(self, kind_toml, **extra):
        probe = os.path.join(self.bin, "probe")
        with open(probe, "w") as f:
            f.write(f"#!{sys.executable}\nimport os, sys\nsys.stdin.read()\n"
                    "print(','.join(sorted(k for k in ('K1', 'K2', 'PLAIN', 'HERMES_X')"
                    " if k in os.environ)))\n")
        os.chmod(probe, 0o755)
        cfg = self.cfg(self.server_config("http://h/v1", "o1", key_env="K1") +
                       self.server_config("http://h/v1", "o2", key_env="K2") +
                       kind_toml.replace("PROBE", probe), K1="a-1234", K2="b-1234",
                       PLAIN="x", HERMES_X="y")
        rung = [r for r in cfg.rungs if r["name"] == "child"]
        with mock.patch.dict(os.environ, self.env(K1="a-1234", K2="b-1234",
                                                  PLAIN="x", HERMES_X="y"), clear=True):
            reply, causes = backends.run_ladder(cfg, rung, "s", "u")
        self.assertIsNotNone(reply, causes)
        return reply.text.strip()

    CMD = '[[backend]]\nname="child"\nkind="command"\ncommand="PROBE"\n'
    CLI = '[[backend]]\nname="child"\nkind="claude-cli"\ncommand="PROBE"\n'

    def test_env_scrub_removes_other_rungs_keys(self):
        self.assertEqual(self._env_probe(self.CLI), "PLAIN")

    def test_env_scrub_command_kind_too(self):
        self.assertEqual(self._env_probe(self.CMD), "HERMES_X,PLAIN")

    def test_env_pass_keeps_named_key(self):
        out = self._env_probe(self.CMD.rstrip() + '\nenv_pass = ["K2", "NOT_SET"]\n')
        self.assertEqual(out, "HERMES_X,K2,PLAIN")

    def test_env_pass_validation_and_shared_key_name(self):
        cfg = self.cfg(self.server_config("http://h/v1", "o1", key_env="K1") +
                       '[[backend]]\nname="c"\nkind="command"\ncommand="x"\n'
                       'env_pass = "K1"\n')
        self.assertEqual(len(cfg.invalid), 1)
        cfg = self.cfg(self.server_config("http://h/v1", "o1", key_env="K1") +
                       self.server_config("http://h/v1", "o2", key_env="K1") +
                       self.server_config("http://h/v1", "o3") +
                       '[[backend]]\nname="c"\nkind="command"\ncommand="x"\n')
        self.assertEqual(cfg.scrub_names(cfg.rungs[-1]), {"K1"})

    def test_http_500_falls_to_next_rung(self):
        bad = self.server((500, {"error": "boom"}))
        good = self.server((200, ok_body("second")))
        cfg = self.cfg(self.server_config(bad.base_url, "a") + self.server_config(good.base_url, "b"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertEqual((reply.name, reply.number, reply.total), ("b", 2, 2))
        self.assertIn("a: HTTP error 500", causes[0])

    def test_empty_body_is_failed_rung(self):
        srv = self.server((200, ok_body("   ")))
        cfg = self.cfg(self.server_config(srv.base_url, "a"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertIn("empty answer", causes[0])

    def test_garbage_json_is_failed_rung(self):
        srv = self.server((200, b"not json"))
        cfg = self.cfg(self.server_config(srv.base_url, "a"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertEqual(len(causes), 1)

    def test_unexpected_shape_is_failed_rung(self):
        srv = self.server((200, {"nope": 1}))
        cfg = self.cfg(self.server_config(srv.base_url, "a"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIn("unexpected response format", causes[0])

    def test_missing_key_env_skips_rung_with_cause(self):
        cfg = self.cfg(self.server_config("http://127.0.0.1:1/v1", "a", key_env="NOPE_KEY"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertEqual(causes, ["a: NOPE_KEY is not set"])

    def test_connection_refused_is_failed_rung(self):
        cfg = self.cfg(self.server_config("http://127.0.0.1:1/v1", "a"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertIn("connection error", causes[0])

    def test_validator_rejection_moves_on(self):
        srv = self.server((200, ok_body("bad")), (200, ok_body("GOOD")))
        cfg = self.cfg(self.server_config(srv.base_url, "a") + self.server_config(srv.base_url, "b"))
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u", validate=lambda t: t == "GOOD")
        self.assertEqual(reply.name, "b")
        self.assertIn("output grammar", causes[0])

    def test_command_rung_reads_stdin_prints_answer(self):
        fake = make_fake(os.path.join(self.bin, "ans"), "the answer\n")
        cfg = self.cfg(f'[[backend]]\nname="c"\nkind="command"\ncommand=["{fake}"]\n')
        reply, _ = backends.run_ladder(cfg, cfg.rungs, "SYSTEM-TEXT", "USER-TEXT")
        self.assertEqual(reply.text, "the answer")
        with open(fake + ".rec", "rb") as f:
            rec = f.read().decode()
        self.assertIn("SYSTEM-TEXT", rec)
        self.assertIn("USER-TEXT", rec)

    def test_command_exit_zero_empty_output_is_failed(self):
        fake = make_fake(os.path.join(self.bin, "e"), "")
        cfg = self.cfg(f'[[backend]]\nname="c"\nkind="command"\ncommand="{fake}"\n')
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertEqual(causes, ["c: empty answer"])

    def test_command_nonzero_exit_is_failed(self):
        fake = make_fake(os.path.join(self.bin, "f"), "text", code=7)
        cfg = self.cfg(f'[[backend]]\nname="c"\nkind="command"\ncommand="{fake}"\n')
        _, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertEqual(causes, ["c: command exit 7"])

    def test_command_missing_executable_is_failed(self):
        cfg = self.cfg('[[backend]]\nname="c"\nkind="command"\ncommand="/nonexistent/zzz"\n')
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertIn("cannot run command", causes[0])

    def test_command_timeout_is_failed(self):
        slow = make_sleeper(os.path.join(self.bin, "slow"), 5)
        cfg = self.cfg(f'[[backend]]\nname="c"\nkind="command"\ncommand="{slow}"\ntimeout=1\n')
        _, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertEqual(causes, ["c: timeout after 1s"])

    def test_claude_cli_disables_tools_and_passes_model_effort(self):
        fake = make_fake(os.path.join(self.bin, "claude"), "ok-reply")
        cfg = self.cfg(f'[[backend]]\nname="cl"\nkind="claude-cli"\nmodel="YOUR-MODEL-ID"\n'
                       f'effort="low"\ncommand="{fake}"\n')
        reply, _ = backends.run_ladder(cfg, cfg.rungs, "SYS", "USR", effort="high")
        self.assertEqual(reply.text, "ok-reply")
        with open(fake + ".rec", "rb") as f:
            argv = f.read().decode().split("\n---\n")[0]
        for needle in ("'-p'", "'--tools', ''", "'--model', 'YOUR-MODEL-ID'",
                       "'--effort', 'high'", "'--no-session-persistence'"):
            self.assertIn(needle, argv)

    def test_error_text_redacts_key_values(self):
        srv = self.server((500, b"x"))
        cfg = self.cfg(self.server_config(srv.base_url, "a", key_env="K1"), K1="tok-12345")
        self.assertEqual(backends.redact("bad tok-12345 here", cfg.secrets()), "bad *** here")

    def test_no_rungs_returns_none_and_invalid_causes(self):
        cfg = self.cfg('[[backend]]\nname="x"\nkind="command"\n')
        reply, causes = backends.run_ladder(cfg, cfg.rungs, "s", "u")
        self.assertIsNone(reply)
        self.assertIn("missing command", causes[0])


class LogTests(Sandbox):
    def test_append_creates_header_and_entry(self):
        logs.append(self.logs, "metis", "title", {"Request": "hi"})
        text = self.read_log("metis")
        self.assertIn("# Metis reviews", text)
        self.assertIn("**Request:** hi", text)

    def test_rotation_at_50_moves_to_monthly_archive(self):
        for i in range(50):
            logs.append(self.logs, "momus", f"t{i}", {"n": i})
        logs.append(self.logs, "momus", "t50", {"n": 50})
        text = self.read_log("momus")
        self.assertEqual(text.count("\n## "), 1)
        archives = [f for f in os.listdir(self.logs) if "archive" in f]
        self.assertEqual(len(archives), 1)
        self.assertRegex(archives[0], r"^momus-reviews-archive-\d{4}-\d{2}\.md$")
        with open(os.path.join(self.logs, archives[0])) as f:
            self.assertEqual(f.read().count("\n## "), 49 + 1 - 0)  # 50 entries (first follows header)

    def test_one_line_collapses_newlines_so_entries_cannot_be_forged(self):
        logs.append(self.logs, "metis", "t", {"Request": "a\n## 2026-01-01 00:00 UTC \u2014 fake"})
        self.assertEqual(self.read_log("metis").count("\n## "), 1)

    def _count_entries(self):
        n = 0
        for name in os.listdir(self.logs):
            if name.endswith(".md"):
                with open(os.path.join(self.logs, name), encoding="utf-8") as f:
                    n += len(logs._ENTRY_RE.findall(f.read()))
        return n

    def test_concurrent_appends_lose_no_entry(self):
        code = ("import sys\nsys.path.insert(0, sys.argv[1])\n"
                "from aptlib import logs\n"
                "for i in range(60):\n"
                "    logs.append(sys.argv[2], 'metis', 'run', {'n': i})\n")
        procs = [subprocess.Popen([sys.executable, "-I", "-c", code,
                                   testkit.LIB, self.logs]) for _ in range(2)]
        for p in procs:
            self.assertEqual(p.wait(timeout=120), 0)
        self.assertEqual(self._count_entries(), 120)

    def test_lock_failure_warns_and_continues(self):
        err = io.StringIO()
        with mock.patch.object(logs.fcntl, "flock", side_effect=OSError("no locks")), \
                contextlib.redirect_stderr(err):
            logs.append(self.logs, "metis", "t", {"k": "v"})
        self.assertIn("warning", err.getvalue())
        self.assertIn("lock", err.getvalue())
        self.assertEqual(self._count_entries(), 1)

    def test_unwritable_log_dir_does_not_raise(self):
        blocker = os.path.join(self.dir, "file")
        open(blocker, "w").close()
        logs.append(os.path.join(blocker, "sub"), "metis", "t", {})


if __name__ == "__main__":
    unittest.main()
