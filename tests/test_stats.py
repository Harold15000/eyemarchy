"""Tests for scripts/stats.py against a fake /sys and /proc."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import stats  # noqa: E402


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class FakeSys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def hwmon(self, n, name, files):
        write(self.root, f"class/hwmon/hwmon{n}/name", name)
        for k, v in files.items():
            write(self.root, f"class/hwmon/hwmon{n}/{k}", v)

    def test_intel_package_temp(self):
        self.hwmon(0, "acpitz", {"temp1_input": "40000"})
        self.hwmon(1, "coretemp", {"temp1_label": "Package id 0", "temp1_input": "61000",
                                   "temp2_label": "Core 0", "temp2_input": "58000"})
        self.assertEqual(stats.cpu_temp(self.root), 61.0)

    def test_amd_prefers_tdie(self):
        self.hwmon(0, "k10temp", {"temp1_label": "Tctl", "temp1_input": "75000",
                                  "temp2_label": "Tdie", "temp2_input": "48000"})
        self.assertEqual(stats.cpu_temp(self.root), 48.0)

    def test_no_sensor(self):
        self.assertIsNone(stats.cpu_temp(self.root))

    def test_fans_skip_gpu(self):
        self.hwmon(0, "thinkpad", {"fan1_input": "2400"})
        self.hwmon(1, "amdgpu", {"fan1_input": "900"})
        self.assertEqual(stats.fans(self.root), [2400])

    def test_battery_ignores_device_batteries(self):
        write(self.root, "class/power_supply/hidpp_battery_0/type", "Battery")
        write(self.root, "class/power_supply/hidpp_battery_0/scope", "Device")
        write(self.root, "class/power_supply/hidpp_battery_0/capacity", "55")
        write(self.root, "class/power_supply/BAT0/type", "Battery")
        write(self.root, "class/power_supply/BAT0/capacity", "81")
        write(self.root, "class/power_supply/BAT0/status", "Charging")
        self.assertEqual(stats.battery(self.root), {"percent": 81, "status": "charging"})

    def test_desktop_without_battery(self):
        self.assertIsNone(stats.battery(self.root))

    def test_amd_gpu(self):
        dev = os.path.join(self.root, "devices", "pci0", "0000:03:00.0")
        write(dev, "vendor", "0x1002")
        write(dev, "class", "0x030000")
        write(dev, "gpu_busy_percent", "37")
        write(dev, "mem_info_vram_used", str(2 * 2**30))
        write(dev, "mem_info_vram_total", str(8 * 2**30))
        write(dev, "hwmon/hwmon5/temp1_input", "54000")
        os.makedirs(os.path.join(self.root, "class", "drm"))
        os.symlink(dev, os.path.join(self.root, "class", "drm", "card0"))
        # card0/device must point at the PCI device
        os.unlink(os.path.join(self.root, "class", "drm", "card0"))
        os.makedirs(os.path.join(self.root, "class", "drm", "card0"))
        os.symlink(dev, os.path.join(self.root, "class", "drm", "card0", "device"))
        g = stats.gpu(self.root)
        self.assertEqual(g["vendor"], "amd")
        self.assertEqual(g["util"], 37.0)
        self.assertEqual(g["temp"], 54.0)

    def test_sleeping_nvidia_is_not_woken(self):
        dev = os.path.join(self.root, "devices", "pci0", "0000:01:00.0")
        write(dev, "vendor", "0x10de")
        write(dev, "class", "0x030000")
        write(dev, "power/runtime_status", "suspended")
        os.makedirs(os.path.join(self.root, "class", "drm", "card1"))
        os.symlink(dev, os.path.join(self.root, "class", "drm", "card1", "device"))
        self.assertEqual(stats.gpu(self.root)["state"], "sleep")

    def test_network_counts_physical_interfaces_only(self):
        write(self.root, "proc/net/dev",
              "Inter-| Receive | Transmit\n face |bytes packets|bytes\n"
              "    lo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\n"
              "  eth0: 1000 1 0 0 0 0 0 0 200 1 0 0 0 0 0 0\n"
              "tailscale0: 50 1 0 0 0 0 0 0 50 1 0 0 0 0 0 0\n")
        os.makedirs(os.path.join(self.root, "class", "net", "eth0", "device"))
        os.makedirs(os.path.join(self.root, "class", "net", "lo"))
        net = stats.network(self.root, os.path.join(self.root, "proc"))
        self.assertEqual(net, {"rx": 1000, "tx": 200})


class Live(unittest.TestCase):
    def test_runs_on_this_machine(self):
        out = stats.collect({})
        self.assertIn("mem", out)
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
