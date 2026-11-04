"""Tests for scripts/agents.py. Run with: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import agents  # noqa: E402


def proc(argv, ppid=1, cpu=0):
    return {"ppid": ppid, "cpu": cpu, "argv": argv}


class SshHost(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(agents.ssh_host(["ssh", "box", "hermes"]), "box")

    def test_options_with_values(self):
        argv = ["ssh", "-p", "2222", "-i", "/k", "-t", "me@box", "tmux", "new"]
        self.assertEqual(agents.ssh_host(argv), "me@box")

    def test_glued_option(self):
        self.assertEqual(agents.ssh_host(["ssh", "-p2222", "box"]), "box")

    def test_no_host(self):
        self.assertEqual(agents.ssh_host(["ssh", "-V"]), "")


class RemoteAgents(unittest.TestCase):
    def setUp(self):
        self._rchar = agents.rchar
        agents.rchar = lambda pid, proc=None: 1000

    def tearDown(self):
        agents.rchar = self._rchar

    def test_tmux_profiles_and_dedupe(self):
        procs = {
            10: proc(["ssh", "-t", "homelab", "tmux", "new", "-A", "-s", "hermes-default", "~/.local/bin/hermes"]),
            11: proc(["ssh", "-t", "homelab", "tmux", "new", "-A", "-s", "hermes-work", "~/.local/bin/hermes -p work"]),
            12: proc(["ssh", "-t", "homelab", "tmux", "new", "-A", "-s", "hermes-work", "~/.local/bin/hermes -p work"]),
            13: proc(["ssh", "box", "uptime"]),
        }
        groups = agents.remote_agents(procs, agents.Tracker({}), set())
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["label"], "HERMES · HOMELAB")
        self.assertEqual([a["name"] for a in g["agents"]], ["default", "work"])

    def test_claude_over_ssh(self):
        procs = {20: proc(["ssh", "dev@server", "claude"])}
        groups = agents.remote_agents(procs, agents.Tracker({}), set())
        self.assertEqual(groups[0]["label"], "CLAUDE CODE · SERVER")

    def test_hidden(self):
        procs = {20: proc(["ssh", "server", "claude"])}
        self.assertEqual(agents.remote_agents(procs, agents.Tracker({}), {"remote"}), [])


class ProcessAgents(unittest.TestCase):
    def test_root_only_and_servers_skipped(self):
        procs = {
            100: proc(["/usr/bin/opencode"], ppid=1),
            101: proc(["/usr/bin/opencode", "worker"], ppid=100),
            200: proc(["node", "/usr/lib/node_modules/opencode/bin/opencode", "serve"], ppid=1),
        }
        kids = agents.children_map(procs)
        rows = agents.process_agents(procs, kids, agents.Tracker({}), "opencode", {"opencode"})
        self.assertEqual([r["target"]["pid"] for r in rows], [100])

    def test_interpreter_script(self):
        procs = {300: proc(["node", "/home/u/.npm/bin/gemini"], ppid=1)}
        rows = agents.process_agents(procs, agents.children_map(procs), agents.Tracker({}),
                                     "gemini", {"gemini"})
        self.assertEqual(len(rows), 1)

    def test_custom_regex(self):
        procs = {400: proc(["python3", "-m", "my_agent", "--watch"], ppid=1)}
        groups = agents.custom_agents(procs, agents.children_map(procs), agents.Tracker({}),
                                      [{"name": "My agent", "match": r"-m my_agent"}])
        self.assertEqual(groups[0]["id"], "custom:my-agent")
        self.assertEqual(groups[0]["label"], "MY AGENT")

    def test_custom_bad_regex_is_ignored(self):
        self.assertEqual(agents.custom_agents({}, {}, agents.Tracker({}), [{"name": "x", "match": "("}]), [])


class Tracker(unittest.TestCase):
    def test_working_then_idle(self):
        t = agents.Tracker({"k": {"c": 0, "t": agents.now - 1, "active": 0}})
        state, _ = t.activity("k", 10, threshold_per_s=1)
        self.assertEqual(state, "working")
        t2 = agents.Tracker({"k": {"c": 10, "t": agents.now - 1, "active": agents.now - 60}})
        state, _ = t2.activity("k", 10, threshold_per_s=1)
        self.assertEqual(state, "idle")


class ClaudeSessions(unittest.TestCase):
    def test_states_and_stale_sessions(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as fakeproc:
            sess = os.path.join(home, ".claude", "sessions")
            os.makedirs(sess)
            for pid, status, kind in [(1, "busy", "interactive"), (2, "waiting_for_permission", "interactive"),
                                      (3, "idle", "background"), (4, "busy", "interactive")]:
                with open(os.path.join(sess, f"{pid}.json"), "w") as f:
                    json.dump({"pid": pid, "status": status, "kind": kind, "cwd": f"/src/p{pid}",
                               "sessionId": f"abcdef{pid}0-0000", "statusUpdatedAt": 1}, f)
                if pid != 4:  # pid 4 is a stale file: no such process
                    os.makedirs(os.path.join(fakeproc, str(pid)))
                    with open(os.path.join(fakeproc, str(pid), "cmdline"), "wb") as f:
                        f.write(b"claude\0")
            old = os.environ.pop("CLAUDE_CONFIG_DIR", None)
            try:
                rows = agents.claude_code(agents.Tracker({}), home=home, proc=fakeproc)
            finally:
                if old is not None:
                    os.environ["CLAUDE_CONFIG_DIR"] = old
            states = {r["name"]: r["state"] for r in rows}
            self.assertEqual(states, {"p1": "working", "p2": "waiting", "p3": "idle"})
            bg = [r for r in rows if r["name"] == "p3"][0]
            self.assertEqual(bg["target"]["type"], "attach")
            self.assertEqual(bg["detailCode"], "background")


class Codex(unittest.TestCase):
    def test_threads_from_any_schema(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "state_9.sqlite")
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE threads (id TEXT, title TEXT, cwd TEXT, updated_at INTEGER, archived INTEGER)")
            now = int(time.time())
            con.execute("INSERT INTO threads VALUES ('a', 'Fix tests', '/src/shop', ?, 0)", (now,))
            con.execute("INSERT INTO threads VALUES ('b', 'Old', '/src/x', ?, 0)", (now - 7200,))
            con.execute("INSERT INTO threads VALUES ('c', 'Archived', '/src/y', ?, 1)", (now,))
            con.commit()
            con.close()
            rows = agents.codex_threads(db)
            self.assertEqual([r[0] for r in rows], ["a"])
            self.assertEqual(rows[0][1], "Fix tests")

    def test_latest_db(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".codex"))
            for n in (3, 12, 5):
                open(os.path.join(d, ".codex", f"state_{n}.sqlite"), "w").close()
            old = os.environ.pop("CODEX_HOME", None)
            try:
                self.assertTrue(agents.codex_db(d).endswith("state_12.sqlite"))
            finally:
                if old is not None:
                    os.environ["CODEX_HOME"] = old


class Usage(unittest.TestCase):
    def test_headline_limit(self):
        with tempfile.TemporaryDirectory() as home:
            base = os.path.join(home, "state", "omarchy", "agents", "usage")
            os.makedirs(base)
            with open(os.path.join(base, "claude.json"), "w") as f:
                json.dump({"id": "claude", "limits": [
                    {"label": "Session (5-hour)", "percent": 0.42, "resetsAt": "2999-01-01T00:00:00Z"},
                    {"label": "Weekly (7-day)", "percent": 0.12, "resetsAt": "2999-01-01T00:00:00Z"},
                    {"label": "Expired", "percent": 0.99, "resetsAt": "2000-01-01T00:00:00Z"}]}, f)
            old = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = os.path.join(home, "state")
            try:
                usage = agents.usage_records(home)
            finally:
                if old is None:
                    os.environ.pop("XDG_STATE_HOME")
                else:
                    os.environ["XDG_STATE_HOME"] = old
            self.assertEqual(usage["claude"]["percent"], 0.42)
            self.assertEqual(usage["claude"]["short"], "5h")

    def test_short_window(self):
        self.assertEqual(agents.short_window("Weekly (7-day)"), "7d")
        self.assertEqual(agents.short_window("5 hour session"), "5h")
        self.assertEqual(agents.short_window("Fable Weekly"), "7d")
        self.assertEqual(agents.short_window("Credits"), "")


class Detection(unittest.TestCase):
    def test_program_name(self):
        self.assertTrue(agents.is_cmd(["pi"], {"pi"}))
        self.assertTrue(agents.is_cmd(["/home/u/.local/bin/aider", "--model", "x"], {"aider"}))

    def test_script_of_an_interpreter(self):
        self.assertTrue(agents.is_cmd(["node", "/usr/bin/gemini"], {"gemini"}))
        self.assertTrue(agents.is_cmd(["node", "--no-warnings", "/usr/bin/gemini"], {"gemini"}))
        self.assertTrue(agents.is_cmd(["python3.14", "/home/u/.local/bin/aider"], {"aider"}))
        self.assertTrue(agents.is_cmd(["python3", "-m", "aider"], {"aider"}))

    def test_an_argument_is_not_the_program(self):
        for argv, names in [(["nvim", "pi"], {"pi"}), (["ping", "pi"], {"pi"}),
                            (["less", "goose"], {"goose"}), (["vim", "hermes"], {"hermes"}),
                            (["git", "crush"], {"crush"}), (["python3", "-c", "pi"], {"pi"})]:
            self.assertFalse(agents.is_cmd(argv, names), argv)

    def matcher(self, gid):
        return next(m for g, _, _, m in agents.PROCESS_AGENTS if g == gid)

    def test_shared_names(self):
        goose, copilot = self.matcher("goose"), self.matcher("copilot")
        self.assertTrue(goose(["goose", "session"], 1))
        self.assertFalse(goose(["goose", "postgres", "dbstring", "up"], 1))
        self.assertFalse(goose(["goose", "up"], 1))
        self.assertTrue(copilot(["node", "/usr/bin/copilot"], 1))
        self.assertTrue(copilot(["copilot", "--model", "x"], 1))
        self.assertFalse(copilot(["copilot", "svc", "deploy"], 1))

    def test_amp_is_not_the_editor(self):
        with tempfile.TemporaryDirectory() as fakeproc:
            for pid, exe in [(1, "/usr/bin/amp"), (2, "/home/u/.amp/bin/amp")]:
                os.makedirs(os.path.join(fakeproc, str(pid)))
                os.symlink(exe, os.path.join(fakeproc, str(pid), "exe"))
            self.assertFalse(agents.is_amp(["amp", "notes.txt"], 1, fakeproc))
            self.assertTrue(agents.is_amp(["amp"], 2, fakeproc))
        self.assertTrue(agents.is_amp(["node", "/usr/bin/amp"], 3))

    def test_hermes_launcher(self):
        code = "import sys\nfrom hermes_cli.main import main\nsys.exit(main())"
        hermes = self.matcher("hermes")
        self.assertTrue(hermes(["python3", "-I", "-c", code], 1))
        self.assertTrue(agents.is_server(["python3", "-I", "-c", code, "gateway", "run"]))
        self.assertFalse(agents.is_server(["python3", "-I", "-c", code, "-p", "work"]))
        procs = {1: proc(["python3", "-I", "-c", code], ppid=0),
                 2: proc(["python3", "-I", "-c", code, "gateway", "run"], ppid=0)}
        rows = agents.process_agents(procs, agents.children_map(procs), agents.Tracker({}),
                                     "hermes", {"hermes"}, hermes)
        self.assertEqual([r["target"]["pid"] for r in rows], [1])


def fake_claude(fakeproc, pid, start=500):
    os.makedirs(os.path.join(fakeproc, str(pid)), exist_ok=True)
    with open(os.path.join(fakeproc, str(pid), "cmdline"), "wb") as f:
        f.write(b"claude\0")
    with open(os.path.join(fakeproc, str(pid), "stat"), "w") as f:
        f.write(f"{pid} (claude) S 1 " + " ".join(["0"] * 17) + f" {start} 0\n")


class ClaudeOddFiles(unittest.TestCase):
    def rows(self, sessions):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as fakeproc:
            sess = os.path.join(home, ".claude", "sessions")
            os.makedirs(sess)
            for i, d in enumerate(sessions):
                with open(os.path.join(sess, f"{i}.json"), "w") as f:
                    f.write(d if isinstance(d, str) else json.dumps(d))
                if isinstance(d, dict) and isinstance(d.get("pid"), int):
                    fake_claude(fakeproc, d["pid"])
            old = os.environ.pop("CLAUDE_CONFIG_DIR", None)
            try:
                return agents.claude_code(agents.Tracker({}), home=home, proc=fakeproc)
            finally:
                if old is not None:
                    os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_spare_workers_are_not_sessions(self):
        rows = self.rows([{"pid": 7, "status": "idle", "kind": "bg", "spare": True, "sessionId": "abcd1234"},
                          {"pid": 8, "status": "busy", "kind": "interactive", "cwd": "/src/app"}])
        self.assertEqual([r["name"] for r in rows], ["app"])

    def test_reused_pid(self):
        rows = self.rows([{"pid": 7, "status": "busy", "procStart": 499, "cwd": "/src/old"},
                          {"pid": 8, "status": "busy", "procStart": 500, "cwd": "/src/new"}])
        self.assertEqual([r["name"] for r in rows], ["new"])

    def test_odd_values_do_not_break_the_others(self):
        rows = self.rows(["not json", [1, 2],
                          {"pid": 7, "status": "busy", "statusUpdatedAt": "2026-11-04T10:00:00Z", "cwd": "/src/a"},
                          {"pid": 8, "status": "idle", "name": 42, "cwd": None},
                          {"pid": "x", "status": "busy"}])
        self.assertEqual(sorted(r["name"] for r in rows), ["42", "a"])
        iso = [r for r in rows if r["name"] == "a"][0]
        self.assertEqual(iso["since"], 1793786400000)


class TempRuntime(unittest.TestCase):
    """collect() saves its state: never touch the one of the plugin running here."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._tmp.name

    def tearDown(self):
        if self._env is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._env
        self._tmp.cleanup()


class Robust(TempRuntime):
    def test_odd_usage_records(self):
        with tempfile.TemporaryDirectory() as home:
            base = os.path.join(home, "state", "omarchy", "agents", "usage")
            os.makedirs(base)
            for name, rec in [("a", ["x"]), ("b", {"limits": ["x", 3, None]}), ("c", {"limits": "x"}),
                              ("codex", {"id": "codex", "limits": [{"percent": "0.5", "label": 7}]})]:
                with open(os.path.join(base, name + ".json"), "w") as f:
                    json.dump(rec, f)
            old = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = os.path.join(home, "state")
            try:
                usage = agents.usage_records(home)
            finally:
                if old is None:
                    os.environ.pop("XDG_STATE_HOME")
                else:
                    os.environ["XDG_STATE_HOME"] = old
        self.assertEqual(list(usage), ["codex"])
        self.assertEqual(usage["codex"]["percent"], 0.5)

    def test_a_broken_source_does_not_stop_the_rest(self):
        broken = agents.claude_code
        agents.claude_code = lambda *a, **k: 1 / 0
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                out = agents.collect({"usage": False, "hide": "not a list"})
        finally:
            agents.claude_code = broken
        self.assertNotIn("claude", [g["id"] for g in out["groups"]])

    def test_codex_never_shows_the_first_message(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "state_9.sqlite")
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE threads (id TEXT, title TEXT, preview TEXT, updated_at INTEGER)")
            con.execute("INSERT INTO threads VALUES ('a', '', 'my secret prompt', ?)", (int(time.time()),))
            con.commit()
            con.close()
            self.assertEqual(agents.codex_threads(db)[0][1], "")


class Main(TempRuntime):
    def test_runs_on_this_machine(self):
        out = agents.collect({"usage": False})
        self.assertIn("groups", out)
        json.dumps(out)
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, "eyemarchy", "agents.json")))


if __name__ == "__main__":
    unittest.main()
