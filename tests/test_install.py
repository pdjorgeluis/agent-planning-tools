import json
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "lib"))

from aptlib.testkit import Sandbox, put, ok_body  # noqa: E402

INSTALL = os.path.join(REPO, "install.py")


class InstallBase(Sandbox):
    def setUp(self):
        super().setUp()
        self.prefix = os.path.join(self.dir, "prefix", "nested")  # does not exist yet

    def inst(self, *args, stdin=b""):
        return self.run_script(INSTALL, *args, stdin=stdin)

    def files(self, root=None):
        root = root or self.prefix
        out = []
        for d, _, names in os.walk(root):
            out += [os.path.relpath(os.path.join(d, n), root) for n in names]
        return sorted(out)


class SelectionTests(InstallBase):
    def test_select_only_metis(self):
        rc, out, _ = self.inst("--tools", "metis", "--target", "generic",
                               "--prefix", self.prefix, "--dry-run", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("tools/metis/metis.py", out)
        self.assertNotIn("momus", out)

    def test_select_only_momus(self):
        rc, out, _ = self.inst("--tools", "momus", "--target", "generic",
                               "--prefix", self.prefix, "--dry-run", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("tools/momus/momus.py", out)
        self.assertNotIn("metis", out)

    def test_select_all(self):
        rc, out, _ = self.inst("--tools", "all", "--target", "generic",
                               "--prefix", self.prefix, "--dry-run", "--yes")
        self.assertIn("tools/metis/metis.py", out)
        self.assertIn("tools/momus/momus.py", out)

    def test_real_install_copies_only_chosen_tool_and_lib(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        files = self.files()
        self.assertIn("tools/metis/metis.py", files)
        self.assertIn("lib/aptlib/config.py", files)
        self.assertFalse([f for f in files if "momus" in f])
        self.assertFalse([f for f in files if "test" in f.lower()])  # no tests, no testkit

    def test_no_tools_flag_without_tty_exits_2(self):
        rc, _, err = self.inst("--prefix", self.prefix)
        self.assertEqual(rc, 2)
        self.assertIn("--tools", err)
        self.assertFalse(os.path.exists(self.prefix))

    def test_unknown_target_rejected(self):
        rc, _, err = self.inst("--tools", "all", "--target", "antigravity", "--prefix", self.prefix)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.prefix))


class TargetTests(InstallBase):
    def test_hermes_skill_written_with_root_substituted(self):
        self.inst("--tools", "all", "--target", "hermes", "--prefix", self.prefix, "--yes")
        skill = os.path.join(self.prefix, ".hermes", "skills", "metis", "SKILL.md")
        with open(skill) as f:
            text = f.read()
        self.assertIn(self.prefix, text)
        self.assertNotIn("{{APT_ROOT}}", text)
        self.assertTrue(os.path.exists(os.path.join(self.prefix, ".hermes", "skills", "momus", "SKILL.md")))

    def test_snippet_targets_write_untested_labelled_snippet(self):
        for target, rel in (("codex", ".codex/agent-planning-tools.md"),
                            ("opencode", ".config/opencode/agent-planning-tools.md"),
                            ("generic", "agent-planning-tools-AGENTS.md"),
                            ("claude-code", ".claude/skills/metis/SKILL.md")):
            prefix = os.path.join(self.dir, "p-" + target)
            self.inst("--tools", "metis", "--target", target, "--prefix", prefix, "--yes")
            path = os.path.join(prefix, *rel.split("/"))
            self.assertTrue(os.path.exists(path), target)
        with open(os.path.join(self.dir, "p-codex", ".codex", "agent-planning-tools.md")) as f:
            text = f.read()
        self.assertIn("Tested on Hermes only", text)
        self.assertIn("tools/metis/metis.py", text)
        self.assertNotIn("momus.py", text)

    def test_existing_instruction_file_never_edited(self):
        agents = os.path.join(self.prefix, ".codex", "AGENTS.md")
        os.makedirs(os.path.dirname(agents))
        put(agents, "MY RULES")
        self.inst("--tools", "all", "--target", "codex", "--prefix", self.prefix, "--yes")
        with open(agents) as f:
            self.assertEqual(f.read(), "MY RULES")

    def test_without_prefix_uses_xdg_data_home_and_home_not_real_home(self):
        data = os.path.join(self.dir, "xdg-data")
        p = subprocess.run([sys.executable, "-I", INSTALL, "--tools", "metis", "--target", "hermes", "--yes"],
                           capture_output=True, env=self.env(XDG_DATA_HOME=data), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.exists(os.path.join(data, "agent-planning-tools", "tools", "metis", "metis.py")))
        self.assertTrue(os.path.exists(os.path.join(self.home, ".hermes", "skills", "metis", "SKILL.md")))


class SafetyTests(InstallBase):
    def test_dry_run_writes_nothing(self):
        rc, out, _ = self.inst("--tools", "all", "--prefix", self.prefix, "--dry-run", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("(dry run)", out)
        self.assertFalse(os.path.exists(self.prefix))
        self.assertEqual(os.listdir(self.home), [])

    def test_no_overwrite_without_yes_backs_up(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        target = os.path.join(self.prefix, "tools", "metis", "metis.py")
        put(target, "# my local edit\n")
        rc, out, _ = self.inst("--tools", "metis", "--prefix", self.prefix)
        self.assertEqual(rc, 1)
        self.assertIn("SKIP", out)
        with open(target) as f:
            self.assertEqual(f.read(), "# my local edit\n")
        rc, out, _ = self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        self.assertEqual(rc, 0)
        baks = [f for f in os.listdir(os.path.dirname(target)) if f.startswith("metis.py.bak-")]
        self.assertEqual(len(baks), 1)
        with open(os.path.join(os.path.dirname(target), baks[0])) as f:
            self.assertEqual(f.read(), "# my local edit\n")
        with open(target) as f:
            self.assertIn("Metis", f.read())

    def test_install_twice_is_idempotent(self):
        self.inst("--tools", "all", "--prefix", self.prefix, "--yes")
        before = self.files()
        rc, out, _ = self.inst("--tools", "all", "--prefix", self.prefix)
        self.assertEqual(rc, 0)
        self.assertNotIn("WRITE", out)
        self.assertIn("UNCHANGED", out)
        self.assertEqual(self.files(), before)

    def test_two_installs_merge_manifest(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        self.inst("--tools", "momus", "--prefix", self.prefix, "--yes")
        with open(os.path.join(self.prefix, ".apt-manifest.json")) as f:
            paths = [e["path"] for e in json.load(f)["files"]]
        self.assertTrue(any(p.endswith("metis.py") for p in paths))
        self.assertTrue(any(p.endswith("momus.py") for p in paths))

    def test_corrupt_manifest_refuses(self):
        os.makedirs(self.prefix)
        put(os.path.join(self.prefix, ".apt-manifest.json"), "{not json")
        rc, _, err = self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        self.assertEqual(rc, 2)
        self.assertIn("manifest", err)


class UninstallTests(InstallBase):
    def test_uninstall_leaves_prefix_empty_of_files(self):
        self.inst("--tools", "all", "--target", "hermes", "--prefix", self.prefix, "--yes")
        self.assertGreater(len(self.files()), 10)
        rc, out, _ = self.inst("--uninstall", "--prefix", self.prefix)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.prefix) and self.files())
        self.assertEqual(self.files() if os.path.exists(self.prefix) else [], [])

    def test_uninstall_removes_only_manifest_files(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        stray = os.path.join(self.prefix, "tools", "metis", "notes.txt")
        put(stray, "mine")
        other = os.path.join(self.prefix, "keep.md")
        put(other, "mine too")
        self.inst("--uninstall", "--prefix", self.prefix)
        self.assertEqual(self.files(), ["keep.md", "tools/metis/notes.txt"])

    def test_uninstall_keeps_modified_file_without_yes(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        target = os.path.join(self.prefix, "tools", "metis", "prompt.md")
        put(target, "edited by me")
        rc, out, _ = self.inst("--uninstall", "--prefix", self.prefix)
        self.assertEqual(rc, 1)
        self.assertIn("KEEP", out)
        self.assertTrue(os.path.exists(target))
        rc, _, _ = self.inst("--uninstall", "--prefix", self.prefix, "--yes")
        self.assertEqual(rc, 0)
        self.assertEqual(self.files() if os.path.exists(self.prefix) else [], [])

    def test_uninstall_dry_run_removes_nothing(self):
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        before = self.files()
        rc, out, _ = self.inst("--uninstall", "--dry-run", "--prefix", self.prefix)
        self.assertIn("REMOVE", out)
        self.assertEqual(self.files(), before)

    def test_uninstall_without_manifest_is_a_noop(self):
        os.makedirs(self.prefix)
        put(os.path.join(self.prefix, "x.txt"), "x")
        rc, out, _ = self.inst("--uninstall", "--prefix", self.prefix)
        self.assertEqual(rc, 0)
        self.assertIn("nothing to uninstall", out)
        self.assertEqual(self.files(), ["x.txt"])

    def test_uninstall_removes_target_files_outside_nothing_else(self):
        # without --prefix the skill lands in HOME; uninstall must remove it and keep siblings
        data = os.path.join(self.dir, "xdg-data")
        env = self.env(XDG_DATA_HOME=data)
        sibling = os.path.join(self.home, ".hermes", "skills", "other", "SKILL.md")
        os.makedirs(os.path.dirname(sibling))
        put(sibling, "other skill")
        subprocess.run([sys.executable, "-I", INSTALL, "--tools", "metis", "--target", "hermes", "--yes"],
                       env=env, capture_output=True, timeout=60)
        subprocess.run([sys.executable, "-I", INSTALL, "--uninstall"], env=env, capture_output=True, timeout=60)
        self.assertTrue(os.path.exists(sibling))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".hermes", "skills", "metis")))


class EndToEndTests(InstallBase):
    def test_installed_metis_runs_from_prefix(self):
        srv = self.server((200, ok_body("## Intent\nfine")))
        self.write_config(self.server_config(srv.base_url))
        self.inst("--tools", "metis", "--prefix", self.prefix, "--yes")
        rc, out, _ = self.run_script(os.path.join(self.prefix, "tools", "metis", "metis.py"), "hello")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("[metis] backend=mock"))

    def test_installed_momus_runs_from_prefix(self):
        self.inst("--tools", "momus", "--prefix", self.prefix, "--yes")
        spec = os.path.join(self.work, "s.md")
        put(spec, "nothing cited")
        rc, out, _ = self.run_script(os.path.join(self.prefix, "tools", "momus", "momus.py"),
                                     "--backend", "none", spec)
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("[momus] backend=none"))


if __name__ == "__main__":
    unittest.main()
