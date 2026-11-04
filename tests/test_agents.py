"""Tests for scripts/agents.py. Run with: python3 -m unittest discover -s tests"""
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
            10: proc(["ssh", "-t", "nexus-pc", "tmux", "new", "-A", "-s", "hermes-default", "~/.local/bin/hermes"]),
            11: proc(["ssh", "-t", "nexus-pc", "tmux", "new", "-A", "-s", "hermes-work", "~/.local/bin/hermes -p work"]),
            12: proc(["ssh", "-t", "nexus-pc", "tmux", "new", "-A", "-s", "hermes-work", "~/.local/bin/hermes -p work"]),
            13: proc(["ssh", "box", "uptime"]),
        }
        groups = agents.remote_agents(procs, agents.Tracker({}), set())
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["label"], "HERMES · NEXUS-PC")
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


class Main(unittest.TestCase):
    def test_runs_on_this_machine(self):
        out = agents.collect({"usage": False})
        self.assertIn("groups", out)
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
