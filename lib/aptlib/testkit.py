"""Test helpers shared by every suite: hermetic sandbox, mock HTTP server,
fake executables. Standard library only; no network beyond 127.0.0.1."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(REPO, "lib")


class MockServer:
    """Serves scripted chat-completions replies: a list of (status, body)
    consumed in order; the last one repeats. An item may carry a third
    element, a dict of extra response headers. Records every request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                outer.requests.append({"path": self.path, "raw": raw,
                                       "auth": self.headers.get("Authorization")})
                item = (outer.script.pop(0) if len(outer.script) > 1
                        else outer.script[0])
                status, body = item[0], item[1]
                extra = item[2] if len(item) > 2 else {}
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in extra.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def put(path, text):
    with open(path, "w") as f:
        f.write(text)


def ok_body(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


FAKE_SRC = """#!{py}
import sys
data = sys.stdin.buffer.read()
open({rec!r}, 'wb').write(repr(sys.argv[1:]).encode() + b'\\n---\\n' + data)
sys.stdout.write({reply!r})
sys.exit({code})
"""


def make_fake(path, reply, code=0):
    """Write a fake CLI that records argv+stdin to ``path + '.rec'``."""
    with open(path, "w") as f:
        f.write(FAKE_SRC.format(py=sys.executable, rec=path + ".rec",
                                reply=reply, code=code))
    os.chmod(path, 0o755)
    return path


def make_sleeper(path, seconds):
    with open(path, "w") as f:
        f.write(f"#!{sys.executable}\nimport time\ntime.sleep({seconds})\n")
    os.chmod(path, 0o755)
    return path


class Sandbox(unittest.TestCase):
    """HOME, XDG and logs all live in a temp dir; PATH has no real claude."""

    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="apt-test-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.home = os.path.join(self.dir, "home")
        self.bin = os.path.join(self.dir, "bin")
        self.work = os.path.join(self.dir, "work")
        self.logs = os.path.join(self.dir, "logs")
        for d in (self.home, self.bin, self.work):
            os.makedirs(d)
        self.servers = []
        self.addCleanup(lambda: [s.stop() for s in self.servers])

    def server(self, *script):
        s = MockServer(script)
        self.servers.append(s)
        return s

    def env(self, **extra):
        e = {"HOME": self.home, "XDG_CONFIG_HOME": os.path.join(self.home, ".config"),
             "XDG_STATE_HOME": os.path.join(self.home, ".state"),
             "APT_LOG_DIR": self.logs, "TMPDIR": self.dir,
             "PATH": self.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
             "LANG": "C.UTF-8"}
        e.update(extra)
        return e

    def write_config(self, text):
        path = os.path.join(self.home, ".config", "agent-planning-tools", "config.toml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def run_script(self, script, *args, stdin=b"", **extra):
        p = subprocess.run([sys.executable, "-I", script, *args],
                           input=stdin, capture_output=True, timeout=60,
                           env=self.env(**extra), cwd=self.work)
        return (p.returncode, p.stdout.decode("utf-8", "replace"),
                p.stderr.decode("utf-8", "replace"))

    def read_log(self, tool):
        path = os.path.join(self.logs, f"{tool}-reviews.md")
        with open(path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def server_config(base_url, name="mock", key_env=None, model="MODEL-X"):
        t = (f'[[backend]]\nname = "{name}"\nkind = "openai-compat"\n'
             f'base_url = "{base_url}"\nmodel = "{model}"\n')
        if key_env:
            t += f'api_key_env = "{key_env}"\n'
        return t
