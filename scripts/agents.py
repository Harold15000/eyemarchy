#!/usr/bin/env python3
"""Live status of the AI coding agents running on this machine.

    agents.py [CONFIG_JSON]

Prints one JSON object:

    {"now": ms, "groups": [{"id", "label", "usage", "agents": [...]}]}

Every agent is {"key", "name", "detail", "detailCode", "state", "since", "target"}:

    state   "working" | "waiting" | "idle"
    target  where Enter / click takes you (resolved by act.py)
            {"type": "pid", "pid": N}                    the window that holds that process
            {"type": "attach", "id": "abcd1234", "cwd"}  a background Claude Code session
            {"type": "app", "app": "chatgpt"}            the app window (or launch it)

CONFIG_JSON (all optional):

    {"hide": ["gemini", "remote"],                 group ids to leave out
     "custom": [{"name": "My agent", "match": "regex on the command line"}],
     "remote": true,                               agents started over ssh
     "usage": true}                                plan limits from Omarchy's Agents widget

Sources. Everything is read locally: no network access, and no conversation
content is read except the titles of recent Codex threads.

    Claude Code      ~/.claude/sessions/<pid>.json (real busy / waiting / idle state)
    Codex            ~/.codex/state_*.sqlite thread titles + CPU of the codex engine
    Over ssh         bytes received by `ssh host ... <agent>` (tmux sessions included)
    Everything else  CPU used by the agent's process tree
"""
import glob
import json
import os
import re
import sqlite3
import sys
import time

APP = "eyemarchy"
HOME = os.path.expanduser("~")
PROC = os.environ.get("EYEMARCHY_PROC", "/proc")       # overridable for tests

CLK_TCK = os.sysconf("SC_CLK_TCK")
CPU_WORKING = 0.08        # fraction of one core that counts as "working"
IO_WORKING = 600          # bytes/s received by ssh that count as "working"
HOLD_SECONDS = 6          # keep "working" a few seconds to avoid flicker
CODEX_RECENT = 3600       # Codex threads updated in the last hour

# Command-line agents recognised by their program name.
#   (group id, group label, program names, extra matcher)
PROCESS_AGENTS = [
    ("opencode", "OPENCODE", {"opencode"}, None),
    ("gemini", "GEMINI CLI", {"gemini"}, None),
    ("grok", "GROK", {"grok"}, lambda argv: any("@xai-official/grok" in a for a in argv[:3])),
    ("antigravity", "ANTIGRAVITY", {"antigravity", "agy"}, None),
    ("hermes", "HERMES", {"hermes"}, None),
    ("aider", "AIDER", {"aider"}, None),
    ("amp", "AMP", {"amp"}, None),
    ("crush", "CRUSH", {"crush"}, None),
    ("goose", "GOOSE", {"goose"}, None),
    ("cursor", "CURSOR AGENT", {"cursor-agent"}, None),
    ("qwen", "QWEN CODE", {"qwen"}, None),
    ("copilot", "COPILOT CLI", {"copilot"}, None),
    ("droid", "DROID", {"droid"}, None),
    ("kimi", "KIMI CLI", {"kimi"}, None),
    ("pi", "PI", {"pi"}, None),
]

# Agents that can show up as the remote command of an ssh session.
REMOTE_NAMES = {
    "claude": "CLAUDE CODE", "codex": "CODEX", "opencode": "OPENCODE", "gemini": "GEMINI CLI",
    "hermes": "HERMES", "aider": "AIDER", "amp": "AMP", "crush": "CRUSH", "goose": "GOOSE",
    "cursor-agent": "CURSOR AGENT", "qwen": "QWEN CODE", "copilot": "COPILOT CLI",
    "droid": "DROID", "kimi": "KIMI CLI", "grok": "GROK", "pi": "PI",
}

# Subcommands that start a background server instead of an interactive agent.
SERVER_WORDS = {"serve", "server", "gateway", "dashboard", "daemon", "mcp", "lsp", "acp", "app-server"}

# ssh options that take a value (so the next word is not the host).
SSH_VALUE_OPTS = set("BbcDEeFIiJLlmOoPpQRSWw")

now = time.time()
now_ms = int(now * 1000)


# ------------------------------------------------------------------ helpers

def state_dir():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")))
    return os.path.join(base, APP)


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


def read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except Exception:
        return None


def scan_procs(proc=PROC):
    """{pid: {"ppid", "argv", "cpu" (ticks)}} for the current user's processes."""
    uid = os.getuid()
    procs = {}
    try:
        names = os.listdir(proc)
    except Exception:
        return procs
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            if os.stat(f"{proc}/{pid}").st_uid != uid:
                continue
            stat = read(f"{proc}/{pid}/stat")
            raw = read(f"{proc}/{pid}/cmdline", "rb")
            if not stat or raw is None:
                continue
            rest = stat[stat.rindex(")") + 2:].split()
            procs[pid] = {
                "ppid": int(rest[1]),
                "cpu": int(rest[11]) + int(rest[12]),
                "argv": [a.decode(errors="replace") for a in raw.split(b"\0") if a],
            }
        except Exception:
            continue
    return procs


def children_map(procs):
    kids = {}
    for pid, p in procs.items():
        kids.setdefault(p["ppid"], []).append(pid)
    return kids


def tree_cpu(pid, procs, kids):
    total, stack, seen = 0, [pid], set()
    while stack:
        p = stack.pop()
        if p in seen or p not in procs:
            continue
        seen.add(p)
        total += procs[p]["cpu"]
        stack.extend(kids.get(p, []))
    return total


def ancestors_argv(pid, procs, depth=8):
    out, p = [], procs.get(pid, {}).get("ppid")
    while p and p in procs and depth > 0:
        out.append(" ".join(procs[p]["argv"]))
        p = procs[p]["ppid"]
        depth -= 1
    return out


def cwd_name(pid, proc=PROC):
    try:
        return os.path.basename(os.readlink(f"{proc}/{pid}/cwd")) or "/"
    except Exception:
        return ""


def rchar(pid, proc=PROC):
    txt = read(f"{proc}/{pid}/io")
    if not txt:
        return None
    m = re.search(r"^rchar:\s*(\d+)", txt, re.M)
    return int(m.group(1)) if m else None


def prog(arg):
    """Lower-case program name. Chromium/Electron rewrite their cmdline as a
    single argument with spaces, so cut there."""
    return os.path.basename(arg.split(" ")[0]).lower()


def is_cmd(argv, names):
    """Is argv[0], or the script run by an interpreter (argv[1]), one of names?"""
    return any(prog(a) in names for a in argv[:2])


def is_server(argv):
    return any(a in SERVER_WORDS for a in argv[1:4])


class Tracker:
    """Turns ever-growing counters (CPU, bytes) into a state with hysteresis."""

    def __init__(self, old):
        self.old = old
        self.new = {}

    def activity(self, key, counter, threshold_per_s, min_streak=1):
        """min_streak: readings in a row above the threshold before switching to
        "working" (filters single bursts, such as tmux redrawing)."""
        prev = self.old.get(key, {})
        entry = {"c": counter, "t": now, "streak": 0,
                 "active": prev.get("active", 0), "state": prev.get("state"), "since": prev.get("since")}
        if "c" in prev and now > prev.get("t", now):
            rate = (counter - prev["c"]) / (now - prev["t"])
            if rate >= threshold_per_s:
                entry["streak"] = prev.get("streak", 0) + 1
                if entry["streak"] >= min_streak:
                    entry["active"] = now
        state = "working" if now - entry["active"] < HOLD_SECONDS else "idle"
        self.new[key] = entry
        return self.transition(key, state)

    def transition(self, key, state, since_ms=None):
        entry = self.new.setdefault(key, dict(self.old.get(key, {})))
        if entry.get("state") != state or not entry.get("since"):
            entry["state"] = state
            entry["since"] = since_ms or now_ms
        return state, entry["since"]


def agent(key, name, state, since, target=None, detail="", detail_code=""):
    return {"key": key, "name": name, "detail": detail, "detailCode": detail_code,
            "state": state, "since": since, "target": target or {}}


def pid_target(pid):
    return {"type": "pid", "pid": int(pid)}


STATE_ORDER = {"working": 0, "waiting": 1, "idle": 2}


# ------------------------------------------------------------------ sources

def claude_code(tracker, home=HOME, proc=PROC):
    out = []
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    sess_dir = os.path.join(config, "sessions")
    try:
        files = os.listdir(sess_dir)
    except Exception:
        return out
    for fn in files:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess_dir, fn)) as f:
                d = json.load(f)
            pid = int(d.get("pid", 0))
        except Exception:
            continue
        cmd = read(f"{proc}/{pid}/cmdline", "rb") if pid else None
        if not cmd or b"claude" not in cmd:
            continue  # stale session file
        raw = str(d.get("status", "")).lower()
        if raw == "busy":
            state = "working"
        elif any(w in raw for w in ("wait", "permission", "input", "approval", "blocked")):
            state = "waiting"
        else:
            state = "idle"
        cwd = d.get("cwd") or ""
        name = d.get("name") or os.path.basename(cwd) or f"pid {pid}"
        background = d.get("kind") in ("bg", "background")
        since = d.get("statusUpdatedAt") or d.get("updatedAt") or now_ms
        sid = str(d.get("sessionId", ""))
        key = f"claude:{sid or pid}"
        # Background sessions have no window: they are opened with `claude attach`.
        target = ({"type": "attach", "id": sid[:8], "cwd": cwd or home}
                  if background and sid else pid_target(pid))
        tracker.transition(key, state, int(since))
        out.append(agent(key, name, state, int(since), target,
                         detail="" if background else os.path.basename(cwd),
                         detail_code="background" if background else ""))
    out.sort(key=lambda a: (STATE_ORDER[a["state"]], a["name"].lower()))
    return out


def ssh_host(argv):
    """The destination of an ssh command line (first word that is not an option)."""
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--":
            return argv[i + 1] if i + 1 < len(argv) else ""
        if a.startswith("-") and len(a) > 1:
            letter = a[-1]
            if len(a) == 2 and letter in SSH_VALUE_OPTS:
                i += 2
                continue
            i += 1
            continue
        return a
    return ""


def remote_agents(procs, tracker, hidden):
    """ssh sessions whose remote command runs an agent, e.g.
    `ssh -t box "tmux new -A -s hermes-work hermes -p work"`."""
    out = {}
    for pid, p in procs.items():
        argv = p["argv"]
        if not argv or prog(argv[0]) != "ssh":
            continue
        host = ssh_host(argv)
        if not host:
            continue
        remote = " ".join(argv[argv.index(host) + 1:]) if host in argv else ""
        found = None
        for word in re.findall(r"[\w.-]+", remote):
            base = os.path.basename(word).lower()
            if base in REMOTE_NAMES:
                found = base
                break
            m = re.match(r"([a-z-]+?)[-_]", base)   # tmux session such as hermes-work
            if m and m.group(1) in REMOTE_NAMES:
                found = m.group(1)
                break
        if not found:
            continue
        gid = f"remote:{found}:{host}"
        if "remote" in hidden or gid in hidden:
            continue
        sess = re.search(r"-[st]\s+['\"]?([\w.-]+)", remote)
        profile = re.search(r"(?:^|\s)(?:-p|--profile)\s+['\"]?([\w.-]+)", remote)
        name = (profile.group(1) if profile else "") or \
            (sess.group(1) if sess else "") or found
        if name.lower().startswith(found + "-"):
            name = name[len(found) + 1:] or name
        r = rchar(pid)
        if r is None:
            continue
        key = f"remote:{found}:{host}:{name}"
        state, since = tracker.activity(f"{key}:{pid}", r, IO_WORKING, min_streak=2)
        label = f"{REMOTE_NAMES[found]} · {host.split('@')[-1].upper()}"
        out.setdefault(gid, {"id": gid, "label": label, "agents": []})
        out[gid]["agents"].append(agent(key, name, state, since, pid_target(pid)))
    groups = list(out.values())
    for g in groups:
        # Two terminals attached to the same tmux session are one agent.
        merged = {}
        for a in g["agents"]:
            prev = merged.get(a["name"])
            if prev is None or STATE_ORDER[a["state"]] < STATE_ORDER[prev["state"]]:
                merged[a["name"]] = a
        g["agents"] = sorted(merged.values(), key=lambda a: a["name"])
    groups.sort(key=lambda g: g["label"])
    return groups


def process_agents(procs, kids, tracker, prefix, names=None, match=None, label=None,
                   skip_servers=True):
    """Agents found by process; keeps only the root of each matching tree."""
    hits = set()
    for pid, p in procs.items():
        argv = p["argv"]
        if not argv or prog(argv[0]) == "ssh" or (skip_servers and is_server(argv)):
            continue
        if (names and is_cmd(argv, names)) or (match and match(argv)):
            hits.add(pid)
    roots = [pid for pid in hits if procs[pid]["ppid"] not in hits]
    out = []
    for pid in sorted(roots):
        cpu = tree_cpu(pid, procs, kids) / CLK_TCK
        key = f"{prefix}:{pid}"
        state, since = tracker.activity(key, cpu, CPU_WORKING)
        name = label or cwd_name(pid) or prefix
        out.append(agent(key, name, state, since, pid_target(pid)))
    return out


def codex_db(home):
    base = os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")
    dbs = glob.glob(os.path.join(base, "state_*.sqlite"))

    def version(p):
        m = re.search(r"state_(\d+)\.sqlite$", p)
        return int(m.group(1)) if m else -1
    return max(dbs, key=version) if dbs else None


def codex_threads(db, limit=4):
    """Recent Codex threads, tolerant of schema changes between versions."""
    if not db:
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
        cols = {r[1] for r in con.execute("PRAGMA table_info(threads)")}
        title = [c for c in ("name", "title") if c in cols]
        title_expr = "COALESCE(" + ", ".join([f"NULLIF({c},'')" for c in title] +
                                             (["substr(preview,1,60)"] if "preview" in cols else []) +
                                             ["''"]) + ")"
        updated = "updated_at_ms" if "updated_at_ms" in cols else "updated_at * 1000"
        where = "archived = 0 AND " if "archived" in cols else ""
        cwd = "cwd" if "cwd" in cols else "''"
        rows = con.execute(
            f"SELECT id, {title_expr}, {cwd}, {updated} FROM threads "
            f"WHERE {where}{updated} > ? ORDER BY {updated} DESC LIMIT ?",
            (now_ms - CODEX_RECENT * 1000, limit)).fetchall()
        con.close()
        return rows
    except Exception:
        return []


def codex(procs, kids, tracker, home=HOME):
    # The ChatGPT desktop app (Electron) starts the `codex` engine; the CLI is `codex` too.
    # Only the engine's CPU counts: the UI burns CPU just by being open. Omarchy's own
    # usage collector also starts `codex app-server` briefly; that is not you working.
    app_open = any(p["argv"] and prog(p["argv"][0]) == "chatgpt" for p in procs.values())
    engines = [a for a in process_agents(procs, kids, tracker, "codex-proc", {"codex"},
                                         skip_servers=False)
               if not any("omarchy-agent-usage" in x for x in ancestors_argv(a["target"]["pid"], procs))]
    if not app_open and not engines:
        return []
    busy = any(a["state"] == "working" for a in engines)
    # With the app open, Enter goes to its window; with only the CLI, to its terminal.
    target = ({"type": "app", "app": "chatgpt"} if app_open
              else (engines[0]["target"] if engines else {}))
    threads = []
    for i, (tid, title, cwd, updated) in enumerate(codex_threads(codex_db(home))):
        recent = now_ms - (updated or 0) < 20000
        state = "working" if (busy and i == 0) or recent else "idle"
        key = f"codex:{tid}"
        _, since = tracker.transition(key, state)
        title = (str(title or "").strip().splitlines() or [""])[0][:60]
        threads.append(agent(key, title, state, since, target, detail=os.path.basename(cwd or ""),
                             detail_code="" if title else "untitled"))
    if threads:
        return threads
    # Open but without recent threads: a single row.
    state, since = tracker.transition("codex:open", "working" if busy else "idle")
    return [agent("codex:open", "ChatGPT" if app_open else "Codex", state, since, target)]


def custom_agents(procs, kids, tracker, custom):
    groups = []
    for i, c in enumerate(custom or []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        name = str(c["name"])[:40]
        names = {str(c["process"]).lower()} if c.get("process") else None
        pattern = None
        if c.get("match"):
            try:
                pattern = re.compile(str(c["match"]))
            except re.error:
                continue
        if not names and not pattern:
            continue
        match = (lambda argv, p=pattern: bool(p.search(" ".join(argv)))) if pattern else None
        gid = f"custom:{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or i}"
        rows = process_agents(procs, kids, tracker, gid, names, match)
        if rows:
            groups.append({"id": gid, "label": name.upper(), "agents": rows})
    return groups


# ------------------------------------------------------------------ plan limits

def usage_records(home=HOME):
    """Headline limit per agent from the records Omarchy's Agents widget writes."""
    base = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.join(home, ".local", "state")),
                        "omarchy", "agents", "usage")
    out = {}
    for path in glob.glob(os.path.join(base, "*.json")):
        try:
            with open(path) as f:
                rec = json.load(f)
        except Exception:
            continue
        best = None
        for lim in rec.get("limits") or []:
            try:
                pct = float(lim.get("percent"))
            except (TypeError, ValueError):
                continue
            resets = lim.get("resetsAt") or ""
            reset_at = parse_iso(resets) if resets else None
            if reset_at is not None and reset_at < now:
                continue
            if best is None or pct > best["percent"]:
                best = {"percent": pct, "short": short_window(lim.get("label") or ""), "resetsAt": resets}
        if best:
            out[str(rec.get("id") or os.path.splitext(os.path.basename(path))[0])] = best
    return out


def parse_iso(s):
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def short_window(label):
    low = label.lower()
    m = re.search(r"(\d+)\s*-?\s*(hour|hr|h)\b", low)
    if m:
        return m.group(1) + "h"
    m = re.search(r"(\d+)\s*-?\s*(day|d)\b", low)
    if m:
        return m.group(1) + "d"
    if "week" in low:
        return "7d"
    if "month" in low:
        return "30d"
    return ""


# -------------------------------------------------------------------- main

def collect(config, home=HOME):
    hidden = set(config.get("hide") or [])
    path = os.path.join(state_dir(), "agents.json")
    tracker = Tracker(load_state(path))
    procs = scan_procs()
    kids = children_map(procs)

    groups = [("claude", "CLAUDE CODE", lambda: claude_code(tracker, home)),
              ("codex", "CHATGPT · CODEX", lambda: codex(procs, kids, tracker, home))]
    for gid, label, names, match in PROCESS_AGENTS:
        groups.append((gid, label, lambda n=names, m=match, g=gid:
                       process_agents(procs, kids, tracker, g, n, m)))

    result = []
    for gid, label, fn in groups:
        if gid in hidden:
            continue
        rows = fn()
        if rows:
            result.append({"id": gid, "label": label, "agents": rows})
    if config.get("remote", True):
        result.extend(remote_agents(procs, tracker, hidden))
    result.extend(g for g in custom_agents(procs, kids, tracker, config.get("custom"))
                  if g["id"] not in hidden)

    usage = usage_records(home) if config.get("usage", True) else {}
    for g in result:
        g["usage"] = usage.get(g["id"].split(":")[0]) if not g["id"].startswith("remote:") else None

    save_state(path, tracker.new)
    return {"now": now_ms, "groups": result}


def main(argv):
    try:
        config = json.loads(argv[0]) if argv and argv[0] else {}
        if not isinstance(config, dict):
            config = {}
    except Exception:
        config = {}
    print(json.dumps(collect(config), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
