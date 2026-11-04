.pragma library

// Sample data for `omarchy-shell eyemarchy demo on`: screenshots, recordings
// and trying layouts without starting a dozen agents.

function groups(now) {
  function a(key, name, state, ago, detail) {
    return { key: key, name: name, detail: detail || "", detailCode: "", state: state,
             since: now - ago * 1000, target: {} }
  }
  return [
    { id: "claude", label: "CLAUDE CODE", usage: { percent: 0.42, short: "5h" }, agents: [
      a("demo:c1", "landing-page", "working", 192, "site"),
      a("demo:c2", "api-refactor", "waiting", 45, "backend"),
      a("demo:c3", "release-notes", "idle", 900, "docs")
    ]},
    { id: "codex", label: "CHATGPT · CODEX", usage: { percent: 0.18, short: "7d" }, agents: [
      a("demo:x1", "Fix flaky checkout test", "working", 64, "shop")
    ]},
    { id: "opencode", label: "OPENCODE", usage: null, agents: [
      a("demo:o1", "dotfiles", "idle", 1800)
    ]},
    { id: "remote:hermes:homelab", label: "HERMES · HOMELAB", usage: null, agents: [
      a("demo:h1", "default", "working", 8),
      a("demo:h2", "research", "idle", 3600)
    ]}
  ]
}

var STATS = {
  cpuPct: 23, cpuTemp: 61,
  memTotal: 32 * 1073741824, memUsed: 9.4 * 1073741824,
  gpu: { vendor: "nvidia", name: "RTX 4070", state: "active", util: 37, temp: 54,
         vramUsed: 3.1 * 1073741824, vramTotal: 8 * 1073741824 },
  disks: [{ mount: "/", used: 412 * 1073741824, total: 953 * 1073741824 }],
  fans: [2140, 1870],
  battery: { percent: 82, status: "charging" },
  rxRate: 1.4 * 1048576, txRate: 120 * 1024
}

function top(mode) {
  function it(key, name, detail, code, value, text, closable) {
    return { key: key, pid: 0, start: 0, name: name, detail: detail, detailCode: code,
             value: value, text: text, closable: closable }
  }
  if (mode === "cpu") return [
    it("d1", "Chromium", "4", "windows", 9.2, "9.2%", true),
    it("d2", "Claude Code", "Ghostty", "in", 4.1, "4.1%", true),
    it("system", "", "", "system", 2.6, "2.6%", false),
    it("d3", "Spotify", "", "", 1.2, "1.2%", true),
    it("d4", "Docker", "", "service", 0.6, "0.6%", false)
  ]
  return [
    it("d1", "Chromium", "4", "windows", 3.2e9, "3.2 GB", true),
    it("system", "", "", "system", 1.4e9, "1.4 GB", false),
    it("d2", "Claude Code", "Ghostty", "in", 6.1e8, "610 MB", true),
    it("d3", "Spotify", "", "", 4.4e8, "440 MB", true),
    it("d5", "Obsidian", "", "", 3.1e8, "310 MB", true)
  ]
}
