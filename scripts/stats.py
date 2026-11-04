#!/usr/bin/env python3
"""System readings for the Eyemarchy "System" card.

    stats.py [CONFIG_JSON]        CONFIG_JSON: {"disks": ["/", "/home"]}

Prints one JSON object. Counters (cpu, net) are raw: the card turns two
readings into a rate. Anything the machine does not have is null or empty,
and the card hides that row.

    {"cpu": [user, nice, system, idle, iowait, irq, softirq, steal],
     "cpuTemp": 57.0,
     "mem": {"total": bytes, "available": bytes},
     "gpu": {"vendor", "name", "state": "active"|"sleep", "util", "temp", "vramUsed", "vramTotal"},
     "disks": [{"mount", "used", "total"}],
     "fans": [2068, 1754],
     "battery": {"percent", "status"},
     "net": {"rx": bytes, "tx": bytes}}

Only sysfs, /proc and (for NVIDIA cards that are already awake) nvidia-smi
are read, so a sleeping discrete GPU is never woken up.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

SYS = os.environ.get("EYEMARCHY_SYS", "/sys")
PROC = os.environ.get("EYEMARCHY_PROC", "/proc")

CPU_SENSORS = ["coretemp", "k10temp", "zenpower", "cpu_thermal", "cpu-thermal", "soc_thermal", "acpitz"]
GPU_SENSORS = {"amdgpu", "nouveau", "nvidia", "radeon", "i915", "xe"}
VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def num(path):
    v = read(path)
    try:
        return float(v) if v is not None and v != "" else None
    except ValueError:
        return None


def hwmons(sys_root=SYS):
    out = []
    for h in sorted(glob.glob(f"{sys_root}/class/hwmon/hwmon*")):
        out.append((read(f"{h}/name") or "", h))
    return out


# --------------------------------------------------------------------- cpu

def cpu_counters(proc=PROC):
    line = (read(f"{proc}/stat") or "").splitlines()
    for l in line:
        if l.startswith("cpu "):
            vals = [int(x) for x in l.split()[1:9]]
            return vals + [0] * (8 - len(vals))
    return None


def cpu_temp(sys_root=SYS):
    mons = hwmons(sys_root)
    for want in CPU_SENSORS:
        for name, h in mons:
            if name != want:
                continue
            labels = {}
            for lab in glob.glob(f"{h}/temp*_label"):
                labels[(read(lab) or "").lower()] = lab.replace("_label", "_input")
            # Intel: "Package id 0"; AMD: Tdie (real) before Tctl (offset on some CPUs).
            for key in ("package id 0", "tdie", "tctl"):
                if key in labels:
                    v = num(labels[key])
                    if v:
                        return round(v / 1000, 1)
            v = num(f"{h}/temp1_input")
            if v:
                return round(v / 1000, 1)
    for zone in sorted(glob.glob(f"{sys_root}/class/thermal/thermal_zone*")):
        if read(f"{zone}/type") in ("x86_pkg_temp", "cpu-thermal", "cpu_thermal"):
            v = num(f"{zone}/temp")
            if v:
                return round(v / 1000, 1)
    return None


def memory(proc=PROC):
    vals = {}
    for line in (read(f"{proc}/meminfo") or "").splitlines():
        k, _, rest = line.partition(":")
        if k in ("MemTotal", "MemAvailable"):
            try:
                vals[k] = int(rest.split()[0]) * 1024
            except (IndexError, ValueError):
                pass
    if "MemTotal" not in vals:
        return None
    return {"total": vals["MemTotal"], "available": vals.get("MemAvailable", 0)}


# --------------------------------------------------------------------- gpu

def gpu_devices(sys_root=SYS):
    seen, out = set(), []
    for card in sorted(glob.glob(f"{sys_root}/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card):
            continue  # connectors such as card1-eDP-1
        dev = os.path.realpath(f"{card}/device")
        if dev in seen:
            continue
        seen.add(dev)
        cls = read(f"{dev}/class") or ""
        if not cls.startswith("0x03"):
            continue
        vendor = VENDORS.get(read(f"{dev}/vendor") or "")
        if vendor:
            out.append({"vendor": vendor, "dev": dev})
    return out


def nvidia(dev):
    status = read(f"{dev}/power/runtime_status")
    if status not in (None, "active"):
        return {"vendor": "nvidia", "name": "NVIDIA", "state": "sleep"}
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run(
            [smi, "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3).stdout
        f = [x.strip() for x in out.splitlines()[0].split(",")]
        return {"vendor": "nvidia", "name": short_gpu_name(f[4]), "state": "active",
                "util": float(f[0]), "temp": float(f[1]),
                "vramUsed": float(f[2]) * 2**20, "vramTotal": float(f[3]) * 2**20}
    except Exception:
        return None


def amd(dev):
    util = num(f"{dev}/gpu_busy_percent")
    if util is None:
        return None
    temp = None
    for h in glob.glob(f"{dev}/hwmon/hwmon*"):
        temp = num(f"{h}/temp1_input")
        if temp:
            temp = temp / 1000
            break
    return {"vendor": "amd", "name": "AMD", "state": "active", "util": util, "temp": temp,
            "vramUsed": num(f"{dev}/mem_info_vram_used"), "vramTotal": num(f"{dev}/mem_info_vram_total")}


def short_gpu_name(name):
    for junk in ("NVIDIA ", "GeForce ", "Laptop GPU", " Generation"):
        name = name.replace(junk, "")
    return " ".join(name.split()) or "NVIDIA"


def gpu(sys_root=SYS):
    """The most interesting GPU: a discrete one, even asleep, over an iGPU."""
    best = None
    for d in gpu_devices(sys_root):
        info = nvidia(d["dev"]) if d["vendor"] == "nvidia" else amd(d["dev"]) if d["vendor"] == "amd" else None
        if not info:
            continue
        rank = (2 if d["vendor"] == "nvidia" else 1, info.get("vramTotal") or 0)
        if best is None or rank > best[0]:
            best = (rank, info)
    return best[1] if best else None


# ------------------------------------------------------------------- other

def fs_key(st):
    # btrfs subvolumes (/ and /home on Omarchy) have different st_dev but are
    # one filesystem: compare sizes instead.
    return (st.f_blocks, st.f_frsize, st.f_bfree * st.f_frsize // 2**30)


def disks(mounts):
    out, seen = [], set()
    for m in mounts:
        try:
            st = os.statvfs(m)
        except OSError:
            continue
        if fs_key(st) in seen:
            continue
        seen.add(fs_key(st))
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        out.append({"mount": m, "used": total - free, "total": total})
    return out


def default_mounts():
    mounts = ["/"]
    try:
        if fs_key(os.statvfs("/home")) != fs_key(os.statvfs("/")):
            mounts.append("/home")
    except OSError:
        pass
    return mounts


def fans(sys_root=SYS):
    out = []
    for name, h in hwmons(sys_root):
        if name in GPU_SENSORS:
            continue
        for f in sorted(glob.glob(f"{h}/fan*_input")):
            v = num(f)
            if v is not None:
                out.append(int(v))
    return out[:4]


def battery(sys_root=SYS):
    for p in sorted(glob.glob(f"{sys_root}/class/power_supply/*")):
        if read(f"{p}/type") != "Battery" or read(f"{p}/scope") == "Device":
            continue
        cap = num(f"{p}/capacity")
        if cap is None:
            continue
        return {"percent": int(cap), "status": (read(f"{p}/status") or "").lower()}
    return None


def network(sys_root=SYS, proc=PROC):
    rx = tx = 0
    found = False
    for line in (read(f"{proc}/net/dev") or "").splitlines()[2:]:
        name, _, rest = line.partition(":")
        name = name.strip()
        # Physical interfaces only: tunnels, bridges and containers would count twice.
        if not os.path.exists(f"{sys_root}/class/net/{name}/device"):
            continue
        f = rest.split()
        try:
            rx += int(f[0])
            tx += int(f[8])
            found = True
        except (IndexError, ValueError):
            pass
    return {"rx": rx, "tx": tx} if found else None


def collect(config):
    mounts = config.get("disks") or default_mounts()
    return {"cpu": cpu_counters(), "cpuTemp": cpu_temp(), "mem": memory(), "gpu": gpu(),
            "disks": disks([str(m) for m in mounts][:4]), "fans": fans(),
            "battery": battery(), "net": network()}


def main(argv):
    try:
        config = json.loads(argv[0]) if argv and argv[0] else {}
        if not isinstance(config, dict):
            config = {}
    except Exception:
        config = {}
    print(json.dumps(collect(config)))


if __name__ == "__main__":
    main(sys.argv[1:])
