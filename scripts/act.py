#!/usr/bin/env python3
"""Actions of the Eyemarchy desktop widgets.

    act.py focus-pid <pid>               focus the window that holds that process
    act.py focus-bus <dbus> [entry]      focus the app that owns an MPRIS player
    act.py focus-app <name>              focus an app window (or start the app)
    act.py attach <id> [cwd]             open a terminal with `claude attach <id>`
    act.py close <pid> <start>           close an app with SIGTERM (waits up to 3 s)
    act.py kill <pid> <start>            force it: SIGKILL to its whole process tree
    act.py btop                          open (or focus) the system monitor

Prints one word: ok | nowindow | closed | alive | gone | error

<start> is the starttime field of /proc/<pid>/stat: it prevents killing a
different process if the pid was reused between drawing the list and
confirming the close. Only processes of the current user are ever signalled,
and never the compositor, the shell, audio or anything in the session slice.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
UID = os.getuid()

# Never closed from the widgets, whoever asks.
PROTECTED = {"systemd", "Hyprland", "start-hyprland", "uwsm", "quickshell", "qs",
             "pipewire", "pipewire-pulse", "wireplumber", "dbus-broker", "dbus-daemon",
             "xdg-desktop-portal", "Xwayland"}

# Apps that live in the tray: launching them again brings back their window.
KNOWN_APPS = {"chatgpt": ["chatgpt"]}


def sh(args, timeout=3):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def launch(args):
    """Start detached from the shell: uwsm-app gives it its own scope."""
    if shutil.which("uwsm-app"):
        args = ["uwsm-app", "--"] + args
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def stat(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            s = f.read()
        rest = s[s.rindex(")") + 2:].split()
        return {"state": rest[0], "ppid": int(rest[1]), "start": int(rest[19]),
                "comm": s[s.index("(") + 1:s.rindex(")")]}
    except Exception:
        return None


def ancestors(pid):
    chain = []
    while pid and pid > 1 and pid not in chain:
        chain.append(pid)
        st = stat(pid)
        if not st:
            break
        pid = st["ppid"]
    return chain


def clients():
    try:
        return json.loads(sh(["hyprctl", "clients", "-j"]) or "[]")
    except Exception:
        return []


def pick(cands):
    # The most recently used one (lowest focusHistoryID).
    return sorted(cands, key=lambda c: c.get("focusHistoryID", 1 << 30))[0]


def tmux_clients_for(chain):
    """If the process lives inside tmux, the clients (terminals) of its session."""
    sessions = set()
    for line in sh(["tmux", "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"]).splitlines():
        pid, _, name = line.partition(" ")
        if pid.isdigit() and int(pid) in chain:
            sessions.add(name)
    out = []
    for line in sh(["tmux", "list-clients", "-F", "#{client_pid} #{client_session}"]).splitlines():
        pid, _, name = line.partition(" ")
        if pid.isdigit() and name in sessions:
            out.append(int(pid))
    return out


def window_for(pid):
    by_pid = {}
    for c in clients():
        by_pid.setdefault(c.get("pid"), []).append(c)
    chain = ancestors(int(pid))
    for p in chain:
        if p in by_pid:
            return pick(by_pid[p])
    # Inside tmux the tree climbs to the tmux server, not to the terminal.
    if any((stat(p) or {}).get("comm", "").startswith("tmux") for p in chain):
        for cp in tmux_clients_for(chain):
            for q in ancestors(cp):
                if q in by_pid:
                    return pick(by_pid[q])
    return None


def focus(win):
    addr = win["address"]
    # Hyprland with a Lua config uses hl.dsp.*; older ones the classic dispatcher.
    out = sh(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{addr}" }})'])
    if "ok" not in out.lower():
        out = sh(["hyprctl", "dispatch", "focuswindow", f"address:{addr}"])
    return "ok" if "ok" in out.lower() else "error"


# ------------------------------------------------------------------ actions

def focus_pid(pid):
    win = window_for(pid)
    return focus(win) if win else "nowindow"


def bus_pid(name):
    out = sh(["busctl", "--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
              "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s", name])
    m = re.match(r"u (\d+)", out.strip())
    return int(m.group(1)) if m else None


def focus_bus(name, entry=""):
    if not re.fullmatch(r"[\w.:-]{1,200}", name or ""):
        return "error"
    pid = bus_pid(name)
    entry = (entry or "").lower()
    # After Raise() some apps take a moment to show their window again.
    for _ in range(8):
        win = window_for(pid) if pid else None
        if not win and entry:
            win = next((c for c in clients()
                        if entry in (c.get("class", "") + " " + c.get("initialClass", "")).lower()), None)
        if win:
            return focus(win)
        time.sleep(0.25)
    return "nowindow"


def focus_app(app):
    app = (app or "").lower()
    if app not in KNOWN_APPS:
        return "error"
    for c in clients():
        exe = ""
        try:
            exe = os.readlink(f"/proc/{c.get('pid')}/exe")
        except Exception:
            pass
        if app in (c.get("class", "") + c.get("initialClass", "") + exe).lower():
            return focus(c)
    # No window (it lives in the tray): starting it again shows the running instance.
    launch(KNOWN_APPS[app])
    return "ok"


def find_claude():
    path = os.pathsep.join([os.path.join(HOME, ".local/bin"), os.path.join(HOME, ".claude/local"),
                            os.environ.get("PATH", ""), "/usr/local/bin", "/usr/bin"])
    return shutil.which("claude", path=path) or "claude"


def attach(sid, cwd=""):
    if not re.fullmatch(r"[0-9a-fA-F-]{4,64}", sid or ""):
        return "error"
    # Is a terminal already showing that session? Then focus it.
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/cmdline", "rb") as f:
                args = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        except Exception:
            continue
        if "attach" in args and sid in args and any("claude" in a for a in args[:2]):
            win = window_for(int(name))
            if win:
                return focus(win)
    cwd = cwd if cwd and os.path.isdir(cwd) else HOME
    launch(["xdg-terminal-exec", f"--dir={cwd}", "-e", find_claude(), "attach", sid])
    return "ok"


def descendants(pid):
    """[(pid, starttime)] of every process below pid."""
    kids, starts = {}, {}
    for name in os.listdir("/proc"):
        if name.isdigit():
            st = stat(int(name))
            if st:
                kids.setdefault(st["ppid"], []).append(int(name))
                starts[int(name)] = st["start"]
    out, seen, stack = [], set(), list(kids.get(pid, []))
    while stack:
        p = stack.pop()
        if p not in seen:
            seen.add(p)
            out.append((p, starts[p]))
            stack.extend(kids.get(p, []))
    return out


def alive(pid, start):
    st = stat(pid)
    return st is not None and st["start"] == int(start) and st["state"] not in ("Z", "X")


def send(pid, start, sig):
    """Signal pid only if it is still the process we listed. The pidfd is
    opened first and the start time checked after, so a pid reused in between
    can never receive the signal."""
    fd = None
    try:
        if hasattr(os, "pidfd_open"):
            fd = os.pidfd_open(pid)
        if not alive(pid, start):
            return False
        if fd is not None:
            signal.pidfd_send_signal(fd, sig)
        else:
            os.kill(pid, sig)
        return True
    except OSError:
        return False
    finally:
        if fd is not None:
            os.close(fd)


def closable(pid):
    st = stat(pid)
    if not st or pid <= 1 or st["comm"] in PROTECTED:
        return False
    try:
        if os.stat(f"/proc/{pid}").st_uid != UID:
            return False
        with open(f"/proc/{pid}/cgroup") as f:
            if "/session.slice/" in f.read():
                return False  # Hyprland, the shell, audio...
    except Exception:
        return False
    # Neither the shell that started us nor any of its ancestors.
    return pid not in ancestors(os.getpid())


def close(pid, start):
    pid = int(pid)
    if not alive(pid, start):
        return "gone"
    if not closable(pid):
        return "error"
    if not send(pid, start, signal.SIGTERM):
        return "gone" if not alive(pid, start) else "error"
    for _ in range(30):
        time.sleep(0.1)
        if not alive(pid, start):
            return "closed"
    return "alive"


def kill(pid, start):
    pid = int(pid)
    if not alive(pid, start):
        return "gone"
    if not closable(pid):
        return "error"
    # The app and everything it started, with the same checks for each one.
    for p, s in [(pid, int(start))] + descendants(pid):
        if p == pid or closable(p):
            send(p, s, signal.SIGKILL)
    for _ in range(20):
        time.sleep(0.05)
        if not alive(pid, start):
            return "closed"
    return "alive"


def btop():
    if shutil.which("omarchy-launch-or-focus-tui"):
        launch(["omarchy-launch-or-focus-tui", "btop"])
    else:
        launch(["xdg-terminal-exec", "-e", "btop"])
    return "ok"


def main(args):
    cmd, rest = (args[0] if args else ""), args[1:]
    try:
        if cmd == "focus-pid" and rest:
            return focus_pid(int(rest[0]))
        if cmd == "focus-bus" and rest:
            return focus_bus(rest[0], rest[1] if len(rest) > 1 else "")
        if cmd == "focus-app" and rest:
            return focus_app(rest[0])
        if cmd == "attach" and rest:
            return attach(rest[0], rest[1] if len(rest) > 1 else "")
        if cmd == "close" and len(rest) == 2:
            return close(rest[0], rest[1])
        if cmd == "kill" and len(rest) == 2:
            return kill(rest[0], rest[1])
        if cmd == "btop":
            return btop()
    except Exception:
        return "error"
    return "error"


if __name__ == "__main__":
    print(main(sys.argv[1:]))
