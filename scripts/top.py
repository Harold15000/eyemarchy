#!/usr/bin/env python3
"""Which apps use the most CPU or RAM, grouped by app.

    top.py cpu|ram [LANG]

    -> {"mode", "items": [{"key", "pid", "start", "name", "detail", "detailCode",
                           "value", "closable"}]}

Every process is grouped under its "root": the ancestor started by the
desktop (a child of Hyprland or systemd). Chromium or Spotify count as one
app even with twenty processes, and a terminal includes what runs inside it.
A terminal that serves several windows from one process (Ghostty, kitty or
WezTerm in single-instance mode, foot as a server) is split instead: one row
per program inside, plus one for the terminal itself, so closing a program
never takes the other windows with it.
Hyprland, the shell, PipeWire, the portals and root processes add up to one
"System" row that cannot be closed. Only apps you started can be closed;
services and desktop helpers point to btop instead.

RAM = PSS (each shared page is split between the processes that use it).
CPU = share of the whole machine since the previous call (or over 0.5 s).

detailCode tells the card how to word `detail` in its language:
    "in"         running inside the terminal named in detail
    "windows"    detail is a number of windows
    "service"    a background service
    "background" started by you, running without a window
    "omarchy"    an Omarchy helper
    "system"     the System row
"""
import json
import os
import re
import subprocess
import sys
import time

APP = "eyemarchy"
HOME = os.path.expanduser("~")
UID = os.getuid()
CLK = os.sysconf("SC_CLK_TCK")
NCPU = os.cpu_count() or 1
PAGE = os.sysconf("SC_PAGE_SIZE")
LIMIT = 5

BOUNDARY = {"systemd", "Hyprland", "start-hyprland", "uwsm"}
TERMINALS = {"ghostty", "alacritty", "kitty", "foot", "wezterm-gui", "wezterm",
             "konsole", "gnome-terminal-", "xterm"}
WRAPPERS = {"bash", "zsh", "fish", "sh", "dash", "nu", "setsid", "uwsm-app", "env",
            "xdg-terminal-exec", "timeout", "nohup", "gtk-launch", "tmux"}
SHELLS = {"bash", "sh", "zsh", "dash", "fish"}
INTERPRETERS = {"node", "python", "bun", "deno", "ruby", "perl"}
# Options that run code given on the command line instead of a script.
INLINE = {"node": {"-e", "--eval", "-p", "--print"}, "bun": {"-e", "--eval", "-p", "--print"},
          "deno": {"eval"}, "ruby": {"-e"}, "perl": {"-e", "-E"}}
# Options followed by a value, so that value is not the script.
VALUE_OPTS = {"-W", "-X", "-r", "--require", "--import", "--loader", "--experimental-loader"}
# Desktop helpers: listed, but never offered for closing.
HELPERS = {"udiskie", "hypridle", "hyprsunset", "hyprpaper", "swaybg", "swayosd-server",
           "mako", "walker", "elephant", "waybar", "fcitx5", "voxtype", "hyprpolkitagent",
           "polkit-gnome-au", "gnome-keyring-d", "xdg-desktop-por", "at-spi2-registr"}
PRETTY = {"claude": "Claude Code", "chatgpt": "ChatGPT", "codex": "Codex",
          "ghostty": "Ghostty", "chromium": "Chromium", "spotify": "Spotify",
          "telegram": "Telegram", "nvim": "Neovim", "hermes": "Hermes", "gemini": "Gemini",
          "opencode": "opencode", "grok": "Grok", "antigravity": "Antigravity",
          "voxtype": "Voxtype", "btop": "btop", "ssh": "ssh", "obsidian": "Obsidian",
          "code": "VS Code", "firefox": "Firefox", "steam": "Steam", "discord": "Discord",
          "gnome-keyring-daemon": "Keyring", "fcitx5": "Fcitx5", "udiskie": "Udiskie",
          "localsearch-3": "Local search", "xdg-desktop-portal-gtk": "GTK portal",
          "python": "Python", "python3": "Python", "node": "Node.js", "claude-desktop": "Claude"}
# Omarchy's default web apps, by host.
WEB_APPS = {"youtube.com": "YouTube", "web.whatsapp.com": "WhatsApp", "x.com": "X",
            "app.hey.com": "HEY", "hey.com": "HEY", "github.com": "GitHub", "chatgpt.com": "ChatGPT",
            "claude.ai": "Claude", "discord.com": "Discord", "figma.com": "Figma", "zoom.us": "Zoom",
            "basecamp.com": "Basecamp", "3.basecamp.com": "Basecamp", "mail.google.com": "Gmail",
            "photos.google.com": "Google Photos", "contacts.google.com": "Google Contacts",
            "messages.google.com": "Google Messages", "calendar.google.com": "Google Calendar",
            "docs.google.com": "Google Docs", "gemini.google.com": "Gemini",
            "teams.microsoft.com": "Teams", "outlook.office.com": "Outlook"}


def cache_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get(
        "XDG_CACHE_HOME", os.path.join(HOME, ".cache"))
    return os.path.join(base, APP, "cpu.json")


def read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except Exception:
        return None


def scan():
    procs = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            uid = os.stat(f"/proc/{pid}").st_uid
            s = read(f"/proc/{pid}/stat")
            if not s:
                continue
            i = s.rindex(")")
            rest = s[i + 2:].split()
            procs[pid] = {"uid": uid, "comm": s[s.index("(") + 1:i], "state": rest[0],
                          "ppid": int(rest[1]), "ticks": int(rest[11]) + int(rest[12]),
                          "start": int(rest[19])}
        except Exception:
            continue
    return procs


def argv(pid):
    raw = read(f"/proc/{pid}/cmdline", "rb") or b""
    return [a.decode(errors="replace") for a in raw.split(b"\0") if a]


def cgroup(pid):
    line = (read(f"/proc/{pid}/cgroup") or "").strip()
    m = re.search(r"user@\d+\.service/(.*)$", line)
    return m.group(1) if m else ""


def roots(procs):
    cache = {}

    def root_of(pid):
        path, p = [], pid
        while True:
            if p in cache:
                r = cache[p]
                break
            info = procs.get(p)
            parent = info["ppid"] if info else 0
            pinfo = procs.get(parent)
            if (not info or parent <= 2 or not pinfo or pinfo["uid"] != info["uid"]
                    or pinfo["comm"] in BOUNDARY):
                r = p
                break
            path.append(p)
            p = parent
        for q in path + [p]:
            cache[q] = r
        return r

    return {pid: root_of(pid) for pid in procs}


def is_system(root, procs):
    info = procs[root]
    if info["uid"] != UID or info["ppid"] == 2 or root <= 2:
        return True
    cg = cgroup(root)
    return not cg or cg.startswith("session.slice") or cg.startswith("init.scope")


def ram_of(pid, procs):
    if procs[pid]["uid"] == UID:
        txt = read(f"/proc/{pid}/smaps_rollup")
        if txt:
            m = re.search(r"^Pss:\s+(\d+) kB", txt, re.M)
            if m:
                return int(m.group(1)) * 1024
    statm = read(f"/proc/{pid}/statm") or ""
    try:
        return int(statm.split()[1]) * PAGE
    except Exception:
        return 0


def cpu_values(procs):
    """Share of the whole machine per pid, since the previous sample in the cache."""
    path = cache_path()
    now = time.time()
    try:
        with open(path) as f:
            old = json.load(f)
    except Exception:
        old = {}
    dt = now - old.get("t", 0)
    prev = old.get("p", {})
    if not (0.3 < dt < 10):
        # No recent sample: take one right now.
        prev = {str(p): [i["start"], i["ticks"]] for p, i in procs.items()}
        t0 = time.time()
        time.sleep(0.5)
        fresh = scan()
        for p in list(procs):
            if p in fresh:
                procs[p] = fresh[p]
        now = time.time()
        dt = now - t0
    vals = {}
    for pid, info in procs.items():
        p = prev.get(str(pid))
        if p and p[0] == info["start"]:
            vals[pid] = max(0, info["ticks"] - p[1]) / CLK / dt / NCPU * 100
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump({"t": now, "p": {str(p): [i["start"], i["ticks"]] for p, i in procs.items()}}, f)
        os.replace(path + ".tmp", path)
    except Exception:
        pass
    return vals


def windows():
    try:
        return json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                                         text=True, timeout=2).stdout or "[]")
    except Exception:
        return []


DESKTOP_DIRS = [os.path.join(HOME, ".local/share/applications"), "/usr/share/applications",
                "/var/lib/flatpak/exports/share/applications"]
_wm_classes = None


def name_in(txt, lang):
    # Only the main section: actions ([Desktop Action new-window]) have names too.
    m = re.search(r"^\[Desktop Entry\][^\n]*\n(.*?)(?=^\[|\Z)", txt, re.M | re.S)
    body = m.group(1) if m else txt
    m = (lang and re.search(rf"^Name\[{re.escape(lang)}\]=(.+)$", body, re.M)) or \
        re.search(r"^Name=(.+)$", body, re.M)
    return m.group(1).strip() if m else None


def wm_classes(lang):
    """StartupWMClass -> Name, so web apps (chrome-youtube.com__-Default) get their real name."""
    global _wm_classes
    if _wm_classes is None:
        _wm_classes = {}
        for d in DESKTOP_DIRS:
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for fn in names:
                if not fn.endswith(".desktop"):
                    continue
                txt = read(os.path.join(d, fn)) or ""
                m = re.search(r"^StartupWMClass=(.+)$", txt, re.M)
                if m and m.group(1).strip() not in _wm_classes:
                    name = name_in(txt, lang)
                    if name:
                        _wm_classes[m.group(1).strip()] = name
    return _wm_classes


def desktop_name(cls, lang):
    if not cls:
        return None
    for d in DESKTOP_DIRS:
        for cand in (cls, cls.lower()):
            txt = read(os.path.join(d, cand + ".desktop"))
            if txt and name_in(txt, lang):
                return name_in(txt, lang)
    return wm_classes(lang).get(cls)


def pretty_class(cls):
    m = re.match(r"(?:chrome|chromium|brave|msedge)-([^_]+)__", cls or "")
    if m:  # a Chromium web app without a .desktop file: use the site name
        host = m.group(1).lower()
        if host in WEB_APPS:
            return WEB_APPS[host]
        host = re.sub(r"^(www|web|app|m)\.", "", host)
        if host in WEB_APPS:
            return WEB_APPS[host]
        word = host.split(".")[0]
        return PRETTY.get(word.lower(), word[:1].upper() + word[1:])
    parts = [p for p in re.split(r"[.\-]", cls or "") if p]
    while parts and parts[-1].lower() in ("desktop", "app", "client", "bin"):
        parts.pop()
    word = parts[-1] if parts else (cls or "")
    return PRETTY.get(word.lower(), word[:1].upper() + word[1:])


def clean(text, limit=40):
    """One short line: names come from command lines and window titles."""
    line = (str(text or "").splitlines() or [""])[0]
    return re.sub(r"[\x00-\x1f\x7f]", "", line).strip()[:limit]


def interpreter(name):
    """'python' for python3.14, 'node' for nodejs, the shell for a shell; None otherwise."""
    n = (name or "").lower()
    if n in SHELLS:
        return n
    n = re.sub(r"^(python|ruby|perl)[\d.]*$", r"\1", n)
    n = "node" if n == "nodejs" else n
    return n if n in INTERPRETERS else None


def script_of(interp, a):
    """What an interpreter runs: the script, the module of `python -m`, or ""
    for code given inline (python -c, bash -lc, node -e)."""
    i = 1
    while i < len(a):
        x = a[i]
        if interp == "python" and x == "-m":
            return a[i + 1].split(".")[0] if i + 1 < len(a) else ""
        if x in INLINE.get(interp, ()) or (
                (interp in SHELLS or interp == "python") and re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", x)):
            return ""
        if x in VALUE_OPTS:
            i += 2
            continue
        if x.startswith("-") or (interp in ("bun", "deno") and x == "run"):
            i += 1
            continue
        return x
    return ""


def prog_name(pid, procs):
    """Readable name of a process; for node/python, the name of the script."""
    comm = procs[pid]["comm"]
    a = argv(pid)
    base = os.path.basename(a[0].split(" ")[0]) if a else comm
    interp = interpreter(base) or interpreter(comm)
    if interp and a:
        script = script_of(interp, a)
        if script:
            name = os.path.splitext(os.path.basename(script.rstrip("/")))[0]
            if name in ("index", "cli", "main", "__main__") and "/" in script:
                # .../openclaw/dist/index.js -> openclaw
                parts = [x for x in script.split("/")[:-1] if x]
                while len(parts) > 1 and parts[-1] in ("dist", "build", "lib", "bin", "src", "out"):
                    parts.pop()
                name = parts[-1] if parts else name
            base = name or base
    base = clean(base) or clean(comm)
    return PRETTY.get(base.lower(), base[:1].upper() + base[1:])


def fmt(mode, v):
    if mode == "ram":
        return f"{v / 2**30:.1f} GB" if v >= 2**30 else f"{round(v / 2**20)} MB"
    return f"{v:.1f}%" if v < 10 else f"{round(v)}%"


def exe(pid):
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except Exception:
        return None


def tmux_session(pids):
    """ssh + tmux: the session name says what it is (hermes-work, say)."""
    for p in pids:
        m = re.search(r"\btmux\b.*?-s\s+(\S+)", " ".join(argv(p)))
        if m:
            return m.group(1).strip("'\"")
    return ""


def programs(r, pids, procs):
    """The programs inside terminal r. For every process, the first one below
    the terminal that is not a shell or a wrapper (claude, nvim, ssh...).
    Returns {program pid: the pids of its tree} and the pids of the terminal
    itself (the terminal, its shells)."""
    members = set(pids)
    progs, rest = {}, []
    for p in pids:
        chain, q = [], p
        while q in members and q != r:
            chain.append(q)
            q = procs[q]["ppid"]
        top = next((x for x in reversed(chain)
                    if procs[x]["comm"].lower() not in WRAPPERS | TERMINALS), None)
        if top is None:
            rest.append(p)
        else:
            progs.setdefault(top, []).append(p)
    return progs, rest


def rows_for(r, g, procs, vals, lang):
    """The row of one app, or several for a terminal with several windows."""
    rcomm = procs[r]["comm"]

    def total(pids):
        return sum(vals.get(p, 0) for p in pids)

    def row(pid, name, detail, code, value, closable):
        return {"key": f"{pid}:{procs[pid]['start']}", "pid": pid, "start": procs[pid]["start"],
                "name": clean(name), "detail": clean(detail), "detailCode": code,
                "value": value, "closable": closable}

    # Closable: apps with a window, or started by you even if they live in the
    # tray (own scope or D-Bus activated, like Telegram). User services and
    # Omarchy helpers are not closed from here.
    cg = cgroup(r)
    service = cg.split("/")[-1].endswith(".service") and "app-dbus" not in cg
    helper = rcomm in HELPERS or rcomm.startswith("omarchy") or \
        os.path.basename((argv(r) or [""])[0]).startswith("omarchy")
    closable = not helper and (bool(g["wins"]) or not service)

    if not g["wins"]:
        rep = r
        while procs[rep]["comm"].lower() in WRAPPERS:
            kids = [p for p in g["pids"] if procs[p]["ppid"] == rep]
            if len(kids) != 1:
                break
            rep = kids[0]
        code = "omarchy" if helper and rcomm.startswith("omarchy") else \
            ("service" if service or helper else "background")
        return [row(r, prog_name(rep, procs), "", code, g["value"], closable)]

    w = sorted(g["wins"], key=lambda c: c.get("focusHistoryID", 1 << 30))[0]
    cls = w.get("class") or w.get("initialClass") or ""
    nwin = len(g["wins"])
    if rcomm.lower() not in TERMINALS:
        name = desktop_name(cls, lang) or pretty_class(cls) or prog_name(r, procs)
        if nwin > 1:
            return [row(r, name, str(nwin), "windows", g["value"], closable)]
        return [row(r, name, "", "", g["value"], closable)]

    # A terminal: what runs inside matters (Claude Code, ssh, nvim...).
    own_class = cls.lower().endswith(rcomm.lower())
    term = (desktop_name(cls, lang) if own_class else None) or \
        PRETTY.get(rcomm.lower(), rcomm.capitalize())
    progs, rest = programs(r, g["pids"], procs)
    if nwin > 1:
        # One process serves several windows: closing it would close them
        # all. Each program inside gets its own row (closing it leaves its
        # window at the shell prompt) and the terminal keeps the rest.
        out = []
        for q, pids in progs.items():
            sess = tmux_session(pids)
            out.append(row(q, prog_name(q, procs), sess or term, "" if sess else "in",
                           total(pids), not helper))
        out.append(row(r, term, str(nwin), "windows", total(rest), closable))
        return out
    if not progs:
        return [row(r, term, w.get("title") or "", "", g["value"], closable)]
    top = max(progs, key=lambda q: total(progs[q]))
    name, detail, code = prog_name(top, procs), term, "in"
    if not own_class:
        name = pretty_class(cls)  # a web app or launcher with its own class
        sess = tmux_session(g["pids"])
        if sess:
            detail, code = sess, ""
    # One window: closing the terminal closes just that window.
    return [row(r, name, detail, code, g["value"], closable)]


def build(procs, vals, wins, lang=""):
    """The rows, heaviest first: apps of the user plus one System row."""
    root = roots(procs)
    groups, system = {}, 0.0
    for pid in procs:
        v = vals.get(pid, 0)
        r = root[pid]
        if r not in procs or is_system(r, procs):
            system += v
            continue
        g = groups.setdefault(r, {"value": 0.0, "pids": [], "wins": []})
        g["value"] += v
        g["pids"].append(pid)

    for w in wins:
        r = root.get(w.get("pid"))
        if r in groups:
            groups[r]["wins"].append(w)

    # Stray processes of an app with a window (a Spotify helper left hanging
    # from systemd, say) count towards that app: same executable.
    windowed = {exe(r): r for r, g in groups.items() if g["wins"] and exe(r)}
    for r in [r for r, g in groups.items() if not g["wins"]]:
        owner = windowed.get(exe(r))
        if owner and owner != r:
            groups[owner]["value"] += groups[r]["value"]
            groups[owner]["pids"] += groups.pop(r)["pids"]

    items = [it for r, g in groups.items() for it in rows_for(r, g, procs, vals, lang)]
    items.append({"key": "system", "pid": 0, "start": 0, "name": "", "detail": "",
                  "detailCode": "system", "value": system, "closable": False})
    items.sort(key=lambda it: it["value"], reverse=True)
    return items[:LIMIT]


def main(mode, lang=""):
    procs = scan()
    vals = cpu_values(procs) if mode == "cpu" else {p: ram_of(p, procs) for p in procs}
    items = build(procs, vals, windows(), lang)
    for it in items:
        it["text"] = fmt(mode, it["value"])
    print(json.dumps({"mode": mode, "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    args = sys.argv[1:]
    lang = re.sub(r"[^A-Za-z_]", "", args[1])[:8] if len(args) > 1 else ""
    main("cpu" if (args or ["ram"])[0] == "cpu" else "ram", lang)
