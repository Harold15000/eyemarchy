"""Tests for scripts/top.py. Run with: python3 -m unittest discover -s tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import top  # noqa: E402


def p(comm, ppid, start=None, uid=None):
    return {"uid": top.UID if uid is None else uid, "comm": comm, "state": "S", "ppid": ppid,
            "ticks": 0, "start": start or 1000}


class Fake(unittest.TestCase):
    """build() with a made-up process tree instead of /proc."""

    def setUp(self):
        self.argvs = {}
        self.saved = {n: getattr(top, n) for n in ("argv", "cgroup", "exe", "desktop_name")}
        top.argv = lambda pid: self.argvs.get(pid, [])
        top.cgroup = lambda pid: ("session.slice/wayland-wm.service" if pid == 50
                                  else "app.slice/app-ghostty.scope")
        top.exe = lambda pid: None
        top.desktop_name = lambda cls, lang: "Ghostty" if cls == "com.mitchellh.ghostty" else None

    def tearDown(self):
        for n, f in self.saved.items():
            setattr(top, n, f)

    def terminal(self):
        # Hyprland > ghostty > bash > claude > node (an MCP server)
        #                    > bash > nvim
        #                    > bash
        procs = {50: p("Hyprland", 1), 100: p("ghostty", 50), 101: p("bash", 100),
                 102: p("claude", 101), 103: p("node", 102), 104: p("bash", 100),
                 105: p("nvim", 104), 106: p("bash", 100)}
        self.argvs.update({102: ["claude"], 103: ["node", "/x/mcp/index.js"], 105: ["nvim", "a.txt"]})
        ram = {100: 300, 101: 5, 102: 800, 103: 100, 104: 5, 105: 50, 106: 5}
        return procs, ram

    def win(self, pid=100):
        return {"pid": pid, "class": "com.mitchellh.ghostty", "title": "~", "focusHistoryID": 0}

    def test_terminal_with_several_windows_is_split(self):
        procs, ram = self.terminal()
        rows = {r["name"]: r for r in top.build(procs, ram, [self.win(), self.win()])}
        self.assertEqual(rows["Claude Code"]["pid"], 102)        # closing it stops Claude only
        self.assertEqual(rows["Claude Code"]["value"], 900)
        self.assertEqual(rows["Claude Code"]["detailCode"], "in")
        self.assertEqual(rows["Neovim"]["pid"], 105)
        self.assertEqual(rows["Ghostty"]["pid"], 100)
        self.assertEqual((rows["Ghostty"]["detail"], rows["Ghostty"]["detailCode"]), ("2", "windows"))
        self.assertEqual(rows["Ghostty"]["value"], 315)

    def test_terminal_with_one_window_is_one_row(self):
        procs, ram = self.terminal()
        rows = [r for r in top.build(procs, ram, [self.win()]) if r["key"] != "system"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["name"], rows[0]["detail"], rows[0]["pid"]), ("Claude Code", "Ghostty", 100))
        self.assertEqual(rows[0]["value"], sum(ram.values()))

    def test_system_row(self):
        procs, ram = self.terminal()
        ram[50] = 70
        system = [r for r in top.build(procs, ram, [self.win()]) if r["key"] == "system"][0]
        self.assertEqual(system["value"], 70)
        self.assertFalse(system["closable"])


class ProgName(unittest.TestCase):
    def name(self, argv, comm=None):
        saved = top.argv
        top.argv = lambda pid: argv
        try:
            return top.prog_name(1, {1: p(comm or os.path.basename(argv[0])[:15], 0)})
        finally:
            top.argv = saved

    def test_scripts(self):
        self.assertEqual(self.name(["node", "/usr/bin/gemini"]), "Gemini")
        self.assertEqual(self.name(["python3", "-u", "/home/u/bin/backup.py"]), "Backup")
        self.assertEqual(self.name(["node", "/usr/lib/node_modules/openclaw/dist/index.js", "gateway"]), "Openclaw")
        self.assertEqual(self.name(["python3.14", "-m", "http.server", "8000"]), "Http")
        self.assertEqual(self.name(["bash", "/home/u/deploy.sh"]), "Deploy")
        self.assertEqual(self.name(["bun", "run", "/src/app/server.ts"]), "Server")

    def test_inline_code_is_not_a_name(self):
        code = "import os, sys\nfrom thing import main\nmain()"
        self.assertEqual(self.name(["/opt/python/bin/python3", "-I", "-c", code, "run"]), "Python")
        self.assertEqual(self.name(["bash", "-lc", "sleep 1; echo done"]), "Bash")
        self.assertEqual(self.name(["node", "-e", "console.log(1)"]), "Node.js")

    def test_always_one_short_line(self):
        n = self.name(["weird\nname with a very long text that goes on and on and on"])
        self.assertNotIn("\n", n)
        self.assertLessEqual(len(n), 40)


class DesktopFiles(unittest.TestCase):
    def test_the_app_name_not_an_action_name(self):
        txt = ("[Desktop Entry]\nName=Google Chrome\nExec=chrome\n\n"
               "[Desktop Action new-window]\nName=New Window\nName[es]=Nueva ventana\n")
        self.assertEqual(top.name_in(txt, "es"), "Google Chrome")
        self.assertEqual(top.name_in("[Desktop Entry]\nName=Files\nName[es]=Archivos\n", "es"), "Archivos")


if __name__ == "__main__":
    unittest.main()
