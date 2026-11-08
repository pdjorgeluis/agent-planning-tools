import os
import shutil
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "lib"))

from aptlib.testkit import Sandbox, put  # noqa: E402

SCAN = os.path.join(REPO, "scripts", "privacy-scan.py")
J = "".join

# Forbidden literals are assembled here at run time, never written whole.
FIXTURES = {
    "private key header": J(["-----BEGIN ", "RSA PRIVATE ", "KEY-----"]),
    "secret key prefix (sk)": J(["s", "k-", "abcdefghijklmnop"]),
    "github token prefix": J(["gh", "p_", "abcdefghij0123456789"]),
    "github token prefix (fine)": J(["github_", "pat_", "abcdefghij0123"]),
    "slack token prefix": J(["x", "ox", "b-abcdefghij"]),
    "long token near a secret word": J(["api_", "key = ", "A" * 40]),
    "home directory path": J(["/ho", "me/", "someone/notes"]),
    "email address": J(["a.b", "@", "example", ".org"]),
    "private IPv4 address": J(["192", ".168", ".1.20"]),
    "8-10 digit id": J(["id ", "12345", "67890"]),
}


class ScanBase(Sandbox):
    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.dir, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")

    def g(self, *args):
        cmd = ["git", "-C", self.repo, "-c", "user.name=t", "-c",
               "user.email=" + J(["author", "@", "example", ".org"]), *args]
        p = subprocess.run(cmd, capture_output=True, env=self.env(), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.decode()

    def commit(self, message="c"):
        self.g("add", "-A")
        self.g("commit", "-q", "--allow-empty", "-m", message)

    def scan(self, *args):
        p = subprocess.run([sys.executable, "-I", SCAN, "--root", self.repo, *args],
                           capture_output=True, env=self.env(), timeout=60)
        return p.returncode, p.stdout.decode(), p.stderr.decode()

    def terms(self, *terms):
        path = os.path.join(self.dir, "terms.txt")
        put(path, "\n".join(terms) + "\n")
        return path


class PatternTests(ScanBase):
    def test_clean_repo_exits_0(self):
        put(os.path.join(self.repo, "a.md"), "hello world, nothing here\n")
        self.commit()
        rc, out, _ = self.scan()
        self.assertEqual(rc, 0)
        self.assertIn("clean", out)

    def test_every_pattern_kind_is_caught(self):
        for kind, text in FIXTURES.items():
            with self.subTest(kind=kind):
                self.setUp()
                put(os.path.join(self.repo, "f.txt"), f"line one\n{text}\n")
                rc, out, _ = self.scan()
                self.assertEqual(rc, 1, kind)
                self.assertIn("f.txt:2:", out)
                self.assertNotIn(text, out)  # never echoes the match

    def test_fake_placeholder_values_pass(self):
        put(os.path.join(self.repo, "d.md"), "set YOUR_KEY_HERE and export MY_API_KEY=YOUR_KEY_HERE\n")
        rc, _, _ = self.scan()
        self.assertEqual(rc, 0)

    def test_untracked_file_is_scanned(self):
        put(os.path.join(self.repo, "tracked.txt"), "ok\n")
        self.commit()
        put(os.path.join(self.repo, "new.txt"), FIXTURES["email address"] + "\n")
        rc, out, _ = self.scan()
        self.assertEqual(rc, 1)
        self.assertIn("new.txt", out)

    def test_ignored_file_is_not_scanned(self):
        put(os.path.join(self.repo, ".gitignore"), "secret.txt\n")
        put(os.path.join(self.repo, "secret.txt"), FIXTURES["email address"] + "\n")
        rc, _, _ = self.scan()
        self.assertEqual(rc, 0)

    def test_binary_and_non_utf8_do_not_crash(self):
        with open(os.path.join(self.repo, "b.bin"), "wb") as f:
            f.write(b"\xff\xfe\x00\x01 caf\xe9")
        rc, _, _ = self.scan()
        self.assertEqual(rc, 0)


class HistoryTests(ScanBase):
    def test_secret_only_in_history_is_found(self):
        path = os.path.join(self.repo, "f.txt")
        put(path, FIXTURES["secret key prefix (sk)"] + "\n")
        self.commit()
        put(path, "clean now\n")
        self.commit()
        rc, out, _ = self.scan()
        self.assertEqual(rc, 1)
        self.assertIn("history:f.txt", out)

    def test_commit_header_email_is_excluded(self):
        put(os.path.join(self.repo, "f.txt"), "clean\n")
        self.commit()  # author email is an example address, in the header only
        rc, _, _ = self.scan()
        self.assertEqual(rc, 0)


class MessageTests(ScanBase):
    def test_scan_flags_term_in_commit_message(self):
        put(os.path.join(self.repo, "f.txt"), "clean\n")
        self.commit("mention of zorblax in a message")
        rc, out, _ = self.scan("--terms-file", self.terms("zorblax"))
        self.assertEqual(rc, 1)
        self.assertIn("history-message:", out)
        self.assertIn("forbidden term #1", out)
        self.assertNotIn("orblax", out.lower())

    def test_scan_flags_term_in_tag_message(self):
        put(os.path.join(self.repo, "f.txt"), "clean\n")
        self.commit()
        self.g("tag", "-a", "v1", "-m", "release note about zorblax")
        rc, out, _ = self.scan("--terms-file", self.terms("zorblax"))
        self.assertEqual(rc, 1)
        self.assertIn("history-message:", out)

    def test_scan_still_ignores_author_headers(self):
        put(os.path.join(self.repo, "f.txt"), "clean\n")
        self.commit()
        self.g("tag", "-a", "v1", "-m", "fine")
        # the author and tagger identities appear in headers only
        rc, out, _ = self.scan("--terms-file", self.terms(J(["author", "@", "example"])))
        self.assertEqual(rc, 0, out)


class TermsTests(ScanBase):
    def test_term_match_is_case_insensitive_and_not_echoed(self):
        put(os.path.join(self.repo, "f.txt"), "we mention Zorblax here\n")
        rc, out, _ = self.scan("--terms-file", self.terms("zORBLAX"))
        self.assertEqual(rc, 1)
        self.assertIn("forbidden term #1", out)
        self.assertNotIn("orblax", out.lower())

    def test_term_in_file_name_and_history(self):
        put(os.path.join(self.repo, "zorblax-notes.txt"), "x\n")
        rc, out, _ = self.scan("--terms-file", self.terms("zorblax"))
        self.assertEqual(rc, 1)

    def test_terms_via_env_default(self):
        put(os.path.join(self.repo, "f.txt"), "zorblax\n")
        p = subprocess.run([sys.executable, "-I", SCAN, "--root", self.repo], capture_output=True,
                           env=self.env(APT_TERMS_FILE=self.terms("zorblax")), timeout=60)
        self.assertEqual(p.returncode, 1)

    def test_unknown_terms_file_exits_2(self):
        rc, _, err = self.scan("--terms-file", os.path.join(self.dir, "nope.txt"))
        self.assertEqual(rc, 2)
        self.assertIn("terms file", err)

    def test_empty_terms_file_exits_2(self):
        rc, _, err = self.scan("--terms-file", self.terms(""))
        self.assertEqual(rc, 2)

    def test_no_terms_file_warns_but_runs_patterns(self):
        put(os.path.join(self.repo, "f.txt"), "ok\n")
        rc, _, err = self.scan()
        self.assertEqual(rc, 0)
        self.assertIn("pattern checks only", err)


class SelfTests(ScanBase):
    def test_scanner_source_and_its_tests_hold_no_forbidden_literals(self):
        shutil.copy(SCAN, os.path.join(self.repo, "privacy-scan.py"))
        shutil.copy(os.path.abspath(__file__), os.path.join(self.repo, "test_privacy_scan.py"))
        self.commit()
        rc, out, _ = self.scan()
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
