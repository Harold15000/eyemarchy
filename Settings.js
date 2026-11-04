.pragma library

// Settings live inline in the plugin's entry in ~/.config/omarchy/shell.json:
//
//   "plugins": [{ "id": "io.github.harold15000.eyemarchy", "scale": 1.15,
//                 "agents": { "position": "top-right" } }]
//
// Only what differs from these defaults needs to be written there. The
// settings panel (`omarchy-shell eyemarchy settings`) writes it for you.

var SLOTS = ["top-left", "top-center", "top-right", "center", "bottom-left", "bottom-center", "bottom-right"]
var CARDS = ["clock", "agents", "media", "system"]
var SYSTEM_ROWS = ["cpu", "ram", "gpu", "vram", "disk", "fans", "battery", "net"]

var DEFAULTS = {
  language: "auto",           // auto | en | es
  scale: 1,                   // 0.7 - 1.6, on top of Omarchy's font size
  opacity: 0.62,              // card background, 0.2 - 1
  margin: 28,                 // distance from the screen edges, px
  screens: "all",             // "all" | "focused" | ["eDP-1", "DP-2"]
  keyboard: true,             // arrow keys work on an empty desktop
  hideKeeps: ["clock", "media"], // what stays when you hide the widgets
  clock: {
    position: "center",       // a slot above, or "off"
    timeFormat: "HH:mm",      // Qt format: "h:mm AP" for 12 hours
    dateFormat: "",           // "" = the language default
    showDate: true,
    size: 132,
    offset: -40               // px from the vertical center
  },
  agents: {
    position: "top-left",
    maxPerGroup: 5,
    showWhenEmpty: true,
    hide: [],                 // group ids: "claude", "codex", "hermes", "remote", ...
    custom: [],               // [{ "name": "My agent", "match": "regex on the command line" }]
    remote: true,             // agents started over ssh
    usage: true               // plan limits from Omarchy's Agents widget
  },
  media: {
    position: "center",       // in the center slot it sits under the clock
    hideWhenPaused: false
  },
  system: {
    position: "top-right",
    rows: SYSTEM_ROWS.slice(),
    disks: [],                // mount points; [] = "/" (+ "/home" if separate)
    warnPercent: 85,
    warnTemp: 85,
    allowClose: true          // close / force-quit apps from the CPU and RAM lists
  }
}

function isObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

function clone(v) {
  return JSON.parse(JSON.stringify(v))
}

function num(v, fallback, min, max) {
  var n = Number(v)
  if (v === null || v === undefined || v === "" || !isFinite(n)) return fallback
  return Math.max(min, Math.min(max, n))
}

function bool(v, fallback) {
  return typeof v === "boolean" ? v : fallback
}

function str(v, fallback, allowed) {
  if (typeof v !== "string") return fallback
  if (allowed && allowed.indexOf(v) < 0) return fallback
  return v
}

function slot(v, fallback) {
  return str(v, fallback, SLOTS.concat(["off"]))
}

function strings(v, fallback, allowed) {
  if (!Array.isArray(v)) return fallback.slice()
  var out = []
  for (var i = 0; i < v.length; i++) {
    var s = String(v[i])
    if ((!allowed || allowed.indexOf(s) >= 0) && out.indexOf(s) < 0) out.push(s)
  }
  return out
}

function section(entry, key) {
  return isObject(entry) && isObject(entry[key]) ? entry[key] : {}
}

// The full, validated configuration for a raw shell.json entry.
function normalize(entry) {
  var d = DEFAULTS
  var e = isObject(entry) ? entry : {}
  var c = section(e, "clock"), a = section(e, "agents"), m = section(e, "media"), s = section(e, "system")

  // "all", "focused" or a list of output names; an empty list means "all".
  var screens = d.screens
  if (Array.isArray(e.screens)) screens = strings(e.screens, []).length ? strings(e.screens, []) : d.screens
  else if (e.screens === "focused" || e.screens === "all") screens = e.screens

  var custom = []
  if (Array.isArray(a.custom)) {
    for (var i = 0; i < a.custom.length && custom.length < 12; i++) {
      var x = a.custom[i]
      if (isObject(x) && typeof x.name === "string" && (typeof x.match === "string" || typeof x.process === "string"))
        custom.push({ name: x.name, match: x.match || "", process: x.process || "" })
    }
  }

  return {
    language: str(e.language, d.language, ["auto", "en", "es"]),
    scale: num(e.scale, d.scale, 0.7, 1.6),
    opacity: num(e.opacity, d.opacity, 0.2, 1),
    margin: num(e.margin, d.margin, 0, 200),
    screens: screens,
    keyboard: bool(e.keyboard, d.keyboard),
    hideKeeps: strings(e.hideKeeps, d.hideKeeps, CARDS),
    clock: {
      position: slot(c.position, d.clock.position),
      timeFormat: str(c.timeFormat, d.clock.timeFormat),
      dateFormat: str(c.dateFormat, d.clock.dateFormat),
      showDate: bool(c.showDate, d.clock.showDate),
      size: num(c.size, d.clock.size, 40, 400),
      offset: num(c.offset, d.clock.offset, -600, 600)
    },
    agents: {
      position: slot(a.position, d.agents.position),
      maxPerGroup: Math.round(num(a.maxPerGroup, d.agents.maxPerGroup, 1, 20)),
      showWhenEmpty: bool(a.showWhenEmpty, d.agents.showWhenEmpty),
      hide: strings(a.hide, d.agents.hide),
      custom: custom,
      remote: bool(a.remote, d.agents.remote),
      usage: bool(a.usage, d.agents.usage)
    },
    media: {
      position: slot(m.position, d.media.position),
      hideWhenPaused: bool(m.hideWhenPaused, d.media.hideWhenPaused)
    },
    system: {
      position: slot(s.position, d.system.position),
      rows: strings(s.rows, d.system.rows, SYSTEM_ROWS),
      disks: strings(s.disks, d.system.disks),
      warnPercent: num(s.warnPercent, d.system.warnPercent, 1, 100),
      warnTemp: num(s.warnTemp, d.system.warnTemp, 30, 120),
      allowClose: bool(s.allowClose, d.system.allowClose)
    }
  }
}

// What to write back: only the keys that differ from the defaults.
function diff(cfg) {
  function walk(value, base) {
    if (isObject(value) && isObject(base)) {
      var out = {}
      var any = false
      for (var k in value) {
        var sub = walk(value[k], base[k])
        if (sub !== undefined) { out[k] = sub; any = true }
      }
      return any ? out : undefined
    }
    return JSON.stringify(value) === JSON.stringify(base) ? undefined : value
  }
  return walk(cfg, DEFAULTS) || {}
}

// Set a dotted key ("agents.position") on a copy of cfg.
function withValue(cfg, key, value) {
  var next = clone(cfg)
  var parts = key.split(".")
  var o = next
  for (var i = 0; i < parts.length - 1; i++) o = o[parts[i]]
  o[parts[parts.length - 1]] = value
  return next
}

function valueOf(cfg, key) {
  var parts = key.split(".")
  var o = cfg
  for (var i = 0; i < parts.length; i++) {
    if (o === undefined || o === null) return undefined
    o = o[parts[i]]
  }
  return o
}
