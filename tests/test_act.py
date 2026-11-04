"""Tests for scripts/act.py, against real (harmless) child processes."""
import os
import subprocess
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import act  # noqa: E402


class Signals(unittest.TestCase):
    def setUp(self):
        # The cgroup rules depend on the desktop session; here every child is fair game.
        self._closable = act.closable
        act.closable = lambda pid: pid != os.getpid()
        self.children = []

    def tearDown(self):
        act.closable = self._closable
        for c in self.children:
            if c.poll() is None:
                c.kill()
            c.wait()

    def spawn(self, *args):
        c = subprocess.Popen(list(args))
        self.children.append(c)
        for _ in range(50):
            if act.stat(c.pid):
                break
            time.sleep(0.02)
        return c, act.stat(c.pid)["start"]

    def test_close(self):
        c, start = self.spawn("sleep", "30")
        self.assertEqual(act.close(c.pid, start), "closed")

    def test_a_different_process_is_never_signalled(self):
        c, start = self.spawn("sleep", "30")
        self.assertEqual(act.close(c.pid, start + 1), "gone")
        self.assertFalse(act.send(c.pid, start + 1, 15))
        self.assertIsNone(c.poll())

    def test_force_quit_takes_the_whole_tree(self):
        c, start = self.spawn("sh", "-c", "sleep 30 & sleep 30 & wait")
        kids = []
        for _ in range(50):
            kids = act.descendants(c.pid)
            if len(kids) == 2:
                break
            time.sleep(0.02)
        self.assertEqual(len(kids), 2)
        self.assertEqual(act.kill(c.pid, start), "closed")
        for _ in range(50):
            if not any(act.alive(k, s) for k, s in kids):
                break
            time.sleep(0.02)
        self.assertFalse(any(act.alive(k, s) for k, s in kids))


if __name__ == "__main__":
    unittest.main()
