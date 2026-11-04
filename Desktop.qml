import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.Mpris
import QtQuick
import qs.Commons
import "Settings.js" as Settings
import "I18n.js" as I18n
import "Demo.js" as Demo

// Eyemarchy: the empty desktop as a live, keyboard-first dashboard.
//
//   Clock · Agents · Now playing · System, each one in a slot of the screen.
//
// Keyboard
//   - On an empty desktop: arrows move, Enter goes there, Space plays or
//     pauses, Esc clears the selection and "," opens the settings.
//   - `omarchy-shell eyemarchy toggle` (SUPER + ALT + D) brings the widgets
//     above your windows; Esc or a click outside puts them back.
//   - `omarchy-shell eyemarchy toggleHidden` (SUPER + D) hides them.
// Mouse: click any row.
Item {
  id: desk

  // Injected by the Omarchy shell.
  property var shell: null
  property var manifest: null

  readonly property string pluginId: manifest && manifest.id ? String(manifest.id) : "io.github.harold15000.eyemarchy"
  readonly property string home: Quickshell.env("HOME")
  readonly property string dir: decodeURIComponent(Qt.resolvedUrl(".").toString().replace(/^file:\/\//, ""))
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")) + "/" + pluginId

  // ================================================================ settings
  property var entry: ({})
  property string barPosition: "top"
  readonly property var cfg: Settings.normalize(entry)

  FileView {
    path: desk.home + "/.config/omarchy/shell.json"
    watchChanges: true
    printErrors: false
    onLoaded: desk.readShellConfig(text())
    onFileChanged: reload()
  }

  function readShellConfig(raw) {
    try {
      var c = JSON.parse(raw)
      barPosition = (c.bar && c.bar.position) || "top"
      var list = Array.isArray(c.plugins) ? c.plugins : []
      var found = {}
      for (var i = 0; i < list.length; i++)
        if (list[i] && list[i].id === pluginId) found = list[i]
      if (JSON.stringify(found) !== JSON.stringify(entry)) entry = found
    } catch (e) {}
  }

  readonly property bool canSave: !!(shell && shell.updateEntryInline)
  function setOption(key, value) {
    var next = Settings.withValue(cfg, key, value)
    var d = Settings.diff(next)
    entry = Object.assign({ id: pluginId }, d)
    pendingSave = d
    saveTimer.restart()
  }
  property var pendingSave: null
  Timer {
    id: saveTimer
    interval: 400
    onTriggered: {
      if (desk.pendingSave && desk.canSave) desk.shell.updateEntryInline(desk.pluginId, desk.pendingSave)
      desk.pendingSave = null
    }
  }

  // ================================================================ language
  readonly property string lang: I18n.resolve(cfg.language, Qt.locale().name, Quickshell.env("LANG"))
  function tr(key, a, b) { return I18n.tr(lang, key, a, b) }
  readonly property var locale: {
    var sys = Qt.locale().name
    if (sys.indexOf(lang) === 0) return Qt.locale(sys)
    return Qt.locale(lang === "es" ? "es_ES" : "en_US")
  }

  // ================================================================ sizes
  readonly property real s: cfg.scale * Style.fontScale
  function px(v) { return Math.round(v * s) }
  readonly property real panelWidth: px(300)
  readonly property real mediaWidth: px(400)
  readonly property real mediaArtSize: px(84)
  readonly property real margin: Math.round(cfg.margin * Math.max(1, s))
  readonly property real backgroundAlpha: summoned ? Math.max(0.95, cfg.opacity) : cfg.opacity
  readonly property int selectionIdleMs: 10000   // the selection fades on its own
  readonly property int expandIdleMs: 45000      // and the app list folds back

  // ================================================================ visibility
  // Hidden with `toggleHidden` (SUPER + D); cfg.hideKeeps stay on screen.
  property bool userHidden: false
  property bool stateReady: false
  FileView {
    id: stateFile
    path: desk.stateDir + "/state.json"
    printErrors: false
    atomicWrites: true
    onLoaded: {
      try { desk.userHidden = !!JSON.parse(text()).hidden } catch (e) {}
      desk.stateReady = true
    }
    onLoadFailed: desk.stateReady = true
  }
  Process { id: mkState; command: ["mkdir", "-p", desk.stateDir]; running: true }
  function setHidden(v) {
    userHidden = !!v
    stateFile.setText(JSON.stringify({ hidden: userHidden }) + "\n")
  }
  function shown(card) {
    if (cfg[card].position === "off") return false
    return !userHidden || summoned || cfg.hideKeeps.indexOf(card) >= 0
  }

  // Is any of our cards on a screen right now (not covered by windows)?
  readonly property bool anyDesktopVisible: {
    if (summoned) return true
    for (var i = 0; i < wins.length; i++) if (wins[i] && wins[i].wsWindows === 0) return true
    return false
  }

  // ================================================================ summon
  property bool summoned: false
  property string summonMonitor: ""
  // A summon that never takes the keyboard: for recordings on another output.
  property bool previewOnly: false
  property var wins: []

  function summon() {
    var m = Hyprland.focusedMonitor
    summonMonitor = m ? m.name : ""
    previewOnly = false
    summoned = true
    if (!posOf(selected)) selectFirst()
    keyboardNav = true
    bump()
  }
  function dismiss() {
    if (!summoned) return
    summoned = false
    summonMonitor = ""
    previewOnly = false
    armedKey = ""
    settingsOpen = false
  }

  // ================================================================ demo mode
  property bool demo: false
  property double demoStart: 0
  function setDemo(on) {
    demo = !!on
    demoStart = Date.now()
    if (demo) {
      groups = Demo.groups(demoStart)
      applyDemoStats()
      sysReady = true
    } else {
      groups = []
      agentsSig = ""
      lastCpu = null
      lastNet = null
      sysReady = false
    }
  }

  // ================================================================ IPC
  IpcHandler {
    target: "eyemarchy"
    function toggle(): string {
      if (desk.summoned) desk.dismiss()
      else desk.summon()
      return desk.summoned ? "summoned" : "dismissed"
    }
    function summon(): string { desk.summon(); return "summoned" }
    function dismiss(): string { desk.dismiss(); return "dismissed" }
    // Summon on a given monitor without taking the keyboard (drive it with press).
    function preview(monitor: string): string {
      desk.summonMonitor = monitor
      desk.previewOnly = true
      desk.summoned = true
      if (!desk.posOf(desk.selected)) desk.selectFirst()
      desk.keyboardNav = true
      desk.bump()
      return "preview on " + monitor
    }
    function hide(): string { desk.setHidden(true); return "hidden" }
    function show(): string { desk.setHidden(false); return "visible" }
    function toggleHidden(): string { desk.setHidden(!desk.userHidden); return desk.userHidden ? "hidden" : "visible" }
    function settings(): string {
      desk.settingsOpen = true
      desk.settingsIndex = 0
      if (!desk.summoned) desk.summon()
      return "settings"
    }
    function demo(state: string): string {
      desk.setDemo(state === "toggle" ? !desk.demo : state !== "off")
      return desk.demo ? "demo on" : "demo off"
    }
    // Change one setting from a script: `omarchy-shell eyemarchy configure agents.position top-right`.
    // The value is read as JSON when it parses (true, 1.2, ["cpu"]), as text otherwise.
    function configure(key: string, value: string): string {
      if (Settings.valueOf(Settings.DEFAULTS, key) === undefined) return "unknown setting " + key
      var v = value
      try { v = JSON.parse(value) } catch (e) {}
      // The IPC splits arguments on commas, so lists also come as "cpu ram gpu".
      if (Array.isArray(Settings.valueOf(Settings.DEFAULTS, key)) && typeof v === "string")
        v = v.split(/[\s|]+/).filter(function(x) { return x !== "" })
      var next = Settings.normalize(Settings.withValue(desk.cfg, key, v))
      if (JSON.stringify(Settings.valueOf(next, key)) !== JSON.stringify(v)) return "invalid value for " + key
      desk.setOption(key, v)
      return "ok"
    }
    // The effective settings, defaults included.
    function settingsJson(): string { return JSON.stringify(desk.cfg) }
    // Simulated key presses, for scripts and recordings: Up, Down, Left, Right,
    // Return, Space, Escape, Tab, Comma, BracketLeft, BracketRight.
    function press(key: string): string {
      var k = Qt["Key_" + key]
      if (k === undefined) return "unknown key"
      var ev = { key: k, accepted: false }
      desk.handleKey(ev)
      return ev.accepted ? "ok" : "ignored"
    }
    function state(): string {
      var w = []
      for (var i = 0; i < desk.wins.length; i++) {
        var x = desk.wins[i]
        if (x) w.push({ monitor: x.monName, windows: x.wsWindows, deskActive: x.deskActive,
                        summoned: x.isSummoned, focus: x.focusMode, keys: x.hasKeys })
      }
      return JSON.stringify({ version: desk.manifest ? desk.manifest.version : "", language: desk.lang,
                              selected: desk.selected, summoned: desk.summoned, hidden: desk.userHidden,
                              demo: desk.demo, settings: desk.settingsOpen, expanded: desk.expanded,
                              columns: desk.columns, agents: desk.groups.length,
                              player: desk.player ? String(desk.player.identity || "") : "",
                              canSave: desk.canSave, windows: w })
    }
  }

  // ================================================================ Hyprland
  property bool hyprReady: false           // avoids false "empty" right after start
  property var specialOn: ({})             // monitor -> a special workspace is open
  signal kickWanted()
  signal kickApproved()
  property bool kickPending: false
  // Layers that never use the keyboard; any other one (menus, clipboard...) wins.
  readonly property var passiveLayers: ["omarchy-notifications", "omarchy-osd", "omarchy-bar",
    "omarchy-background", "omarchy-bar-move-ghost", "omarchy-bar-drag-ghost",
    "omarchy-keyboard-panel-dismiss", "hyprpaper", "swaybg", "wallpaper"]

  Timer { interval: 2000; running: true; onTriggered: desk.hyprReady = true }

  Process {
    command: ["hyprctl", "monitors", "-j"]
    running: true
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var s = {}
          JSON.parse(text).forEach(function(m) { s[m.name] = !!(m.specialWorkspace && m.specialWorkspace.name) })
          desk.specialOn = s
        } catch (e) {}
      }
    }
  }

  // Before taking the keyboard, make sure no menu is open.
  Process {
    id: layersProc
    command: ["hyprctl", "layers", "-j"]
    stdout: StdioCollector {
      onStreamFinished: {
        var busy = false
        try {
          var d = JSON.parse(text)
          for (var mon in d) {
            var lv = d[mon].levels
            for (var l in lv) {
              if (l !== "2" && l !== "3") continue
              lv[l].forEach(function(s) {
                var ns = String(s.namespace || "")
                if (ns.indexOf("eyemarchy") !== 0 && desk.passiveLayers.indexOf(ns) < 0) busy = true
              })
            }
          }
        } catch (e) { busy = true }
        if (!busy) desk.kickApproved()
        if (desk.kickPending) { desk.kickPending = false; layersProc.running = true }
      }
    }
  }
  function requestKick() {
    if (layersProc.running) kickPending = true
    else layersProc.running = true
  }

  Connections {
    target: Hyprland
    function onFocusedWorkspaceChanged() { desk.dismiss() }
    function onRawEvent(event) {
      var n = event.name
      if (n === "activespecial") {
        var d = String(event.data)
        var comma = d.lastIndexOf(",")
        var s = Object.assign({}, desk.specialOn)
        s[d.slice(comma + 1)] = d.slice(0, comma) !== ""
        desk.specialOn = s
      } else if (n === "closelayer" && String(event.data).indexOf("eyemarchy") !== 0) {
        desk.kickWanted()   // a menu closed: the empty desktop takes the arrows back
      }
    }
  }

  // ================================================================ actions
  Component {
    id: actComp
    Process {
      id: ap
      property var callback: null
      stdout: StdioCollector {
        onStreamFinished: {
          var r = String(text || "").trim()
          if (ap.callback) ap.callback(r)
          Qt.callLater(function() { ap.destroy() })
        }
      }
    }
  }
  function runAct(args, cb) {
    if (demo) { if (cb) cb("ok"); return }
    var p = actComp.createObject(desk, {
      command: ["python3", "-I", desk.dir + "scripts/act.py"].concat(args),
      callback: cb || null
    })
    if (p) p.running = true
  }

  // Jumps to another window: the keyboard is released meanwhile (see focusMode).
  property bool actionPending: false
  Timer { id: actionGuard; interval: 4000; onTriggered: desk.actionPending = false }
  function jump(args, failKey, failText) {
    actionPending = true
    actionGuard.restart()
    runAct(args, function(r) {
      desk.actionPending = false
      actionGuard.stop()
      if (r === "ok") { desk.afterJump(); return }
      desk.flashRow(failKey, r === "nowindow" ? failText : desk.tr("cantOpen"))
      desk.kickWanted()   // no jump: the desktop takes the arrows back
    })
  }

  // Short messages in a row ("no window").
  property var flash: ({})
  function flashRow(key, text) {
    var f = Object.assign({}, flash)
    f[key] = text
    flash = f
    flashTimer.restart()
  }
  Timer { id: flashTimer; interval: 2500; onTriggered: desk.flash = ({}) }

  // ================================================================ agents
  property var groups: []
  property string agentsSig: ""
  property double nowMs: Date.now()
  readonly property int workingCount: countState("working")
  readonly property int waitingCount: countState("waiting")
  readonly property bool agentsActive: shown("agents")

  function countState(st) {
    var n = 0
    for (var i = 0; i < groups.length; i++)
      for (var j = 0; j < groups[i].agents.length; j++)
        if (groups[i].agents[j].state === st) n++
    return n
  }
  function elapsed(since) {
    var sec = Math.max(0, Math.floor((nowMs - since) / 1000))
    if (sec < 60) return sec + "s"
    var m = Math.floor(sec / 60)
    if (m < 60) return m + "m"
    var h = Math.floor(m / 60)
    if (h < 24) return h + "h"
    return Math.floor(h / 24) + "d"
  }
  function stateText(a) {
    if (a.state === "working") return tr("working", elapsed(a.since))
    if (a.state === "waiting") return tr("waiting", elapsed(a.since))
    return tr("idle")
  }
  function agentByKey(k) {
    for (var i = 0; i < groups.length; i++)
      for (var j = 0; j < groups[i].agents.length; j++)
        if (groups[i].agents[j].key === k) return groups[i].agents[j]
    return null
  }

  Process {
    id: agentsProc
    command: ["python3", "-I", desk.dir + "scripts/agents.py", JSON.stringify({
      hide: desk.cfg.agents.hide, custom: desk.cfg.agents.custom,
      remote: desk.cfg.agents.remote, usage: desk.cfg.agents.usage })]
    stdout: StdioCollector {
      onStreamFinished: {
        if (desk.demo) return
        try {
          var data = JSON.parse(text)
          var next = Array.isArray(data.groups) ? data.groups : []
          var sig = JSON.stringify(next)
          if (sig !== desk.agentsSig) {   // do not rebuild rows when nothing changed
            desk.agentsSig = sig
            desk.groups = next
          }
        } catch (e) {
          console.warn("eyemarchy: invalid output from agents.py", e)
        }
      }
    }
  }
  Timer {
    interval: desk.anyDesktopVisible ? 2000 : 6000
    repeat: true
    running: desk.agentsActive && !desk.demo
    triggeredOnStart: true
    onTriggered: if (!agentsProc.running) agentsProc.running = true
  }
  Timer {
    interval: 1000
    repeat: true
    running: (desk.groups.length > 0 || desk.player !== null) && desk.anyDesktopVisible
    onTriggered: desk.nowMs = Date.now()
  }

  // ================================================================ system
  property var lastCpu: null
  property var lastNet: null
  property real cpuPct: 0
  property real cpuTemp: 0
  property real memTotal: 0
  property real memUsed: 0
  property var gpu: null
  property var disks: []
  property var fans: []
  property var battery: null
  property real rxRate: -1
  property real txRate: -1
  property bool sysReady: false
  readonly property bool systemActive: shown("system")

  function gb(bytes) { return (bytes / 1073741824).toFixed(bytes >= 107374182400 ? 0 : 1) }
  function rate(bps) {
    if (bps < 0) return "—"
    if (bps >= 1048576) return (bps / 1048576).toFixed(1) + " MB/s"
    if (bps >= 1024) return Math.round(bps / 1024) + " KB/s"
    return Math.round(bps) + " B/s"
  }

  function applyStats(d) {
    var t = Date.now()
    if (d.cpu && d.cpu.length >= 8) {
      var idle = d.cpu[3] + d.cpu[4]
      var total = 0
      for (var k = 0; k < 8; k++) total += d.cpu[k]
      if (lastCpu) {
        var dt = total - lastCpu.total
        var di = idle - lastCpu.idle
        if (dt > 0) cpuPct = Math.max(0, Math.min(100, 100 * (1 - di / dt)))
      }
      lastCpu = { total: total, idle: idle }
    }
    cpuTemp = d.cpuTemp || 0
    if (d.mem) { memTotal = d.mem.total; memUsed = d.mem.total - d.mem.available }
    gpu = d.gpu || null
    disks = d.disks || []
    fans = d.fans || []
    battery = d.battery || null
    if (d.net) {
      if (lastNet && t > lastNet.t) {
        rxRate = Math.max(0, (d.net.rx - lastNet.rx) * 1000 / (t - lastNet.t))
        txRate = Math.max(0, (d.net.tx - lastNet.tx) * 1000 / (t - lastNet.t))
      }
      lastNet = { rx: d.net.rx, tx: d.net.tx, t: t }
    } else {
      rxRate = -1; txRate = -1
    }
    sysReady = true
  }
  function applyDemoStats() {
    var d = Demo.STATS
    cpuPct = d.cpuPct; cpuTemp = d.cpuTemp
    memTotal = d.memTotal; memUsed = d.memUsed
    gpu = d.gpu; disks = d.disks; fans = d.fans; battery = d.battery
    rxRate = d.rxRate; txRate = d.txRate
  }

  Process {
    id: statsProc
    command: ["python3", "-I", desk.dir + "scripts/stats.py", JSON.stringify({ disks: desk.cfg.system.disks })]
    stdout: StdioCollector {
      onStreamFinished: {
        if (desk.demo) return
        try { desk.applyStats(JSON.parse(text)) } catch (e) { console.warn("eyemarchy: invalid output from stats.py", e) }
      }
    }
  }
  Timer {
    interval: 2000
    repeat: true
    running: desk.systemActive && desk.anyDesktopVisible && !desk.demo
    triggeredOnStart: true
    onTriggered: if (!statsProc.running) statsProc.running = true
  }

  // ---- what uses it (the CPU / RAM lists) ----------------------------------
  property string expanded: ""        // "" | "cpu" | "ram"
  property var topItems: []
  property var appState: ({})         // key -> "closing" | "alive" | "killing"
  property string armedKey: ""        // row waiting for the close confirmation
  property var hovering: ({})

  function setHover(section, on) {
    var h = Object.assign({}, hovering)
    h[section] = on
    hovering = h
    if (on) bump()
  }
  readonly property bool anyHover: !!(hovering.agents || hovering.media || hovering.system || hovering.settings)

  Process {
    id: topProc
    property string mode: ""
    command: ["python3", "-I", desk.dir + "scripts/top.py", mode, desk.lang]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var d = JSON.parse(text)
          // With the pointer on it or a confirmation pending, the list is not reordered.
          if (d.mode === desk.expanded && !desk.armedKey && !desk.hovering.system)
            desk.topItems = d.items
          else if (d.mode === desk.expanded && desk.topItems.length === 0)
            desk.topItems = d.items
        } catch (e) {}
      }
    }
  }
  function refreshTop() {
    if (!expanded) return
    if (demo) { topItems = Demo.top(expanded); return }
    if (topProc.running) return
    topProc.mode = expanded
    topProc.running = true
  }
  Timer {
    interval: 3000
    repeat: true
    running: desk.expanded !== "" && desk.anyDesktopVisible
    triggeredOnStart: true
    onTriggered: desk.refreshTop()
  }
  function toggleExpand(mode) {
    if (expanded === mode) { collapse(); return }
    armedKey = ""
    topItems = []
    expanded = mode
    refreshTop()
  }
  function collapse() {
    if (!expanded) return
    var parentKey = "sys:" + expanded
    var inList = selected.indexOf("app:") === 0 || selected === "sys:monitor"
    expanded = ""
    topItems = []
    armedKey = ""
    if (inList) select(parentKey, keyboardNav)
  }
  function topItemByKey(k) {
    for (var i = 0; i < topItems.length; i++) if (topItems[i].key === k) return topItems[i]
    return null
  }
  function setAppState(k, st) {
    var a = Object.assign({}, appState)
    if (st) a[k] = st
    else delete a[k]
    appState = a
  }
  Timer { id: armTimer; interval: 5000; onTriggered: desk.armedKey = "" }

  function topItemName(it) { return it.detailCode === "system" ? tr("systemRow") : it.name }
  function topItemDetail(it) {
    switch (it.detailCode) {
      case "system": return tr("systemDetail")
      case "in": return tr("inTerm", it.detail)
      case "windows": return tr("nWindows", it.detail)
      case "service": return tr("service")
      case "background": return tr("backgroundApp")
      case "omarchy": return "Omarchy"
      default: return it.detail || ""
    }
  }

  function activateApp(navKey) {
    var it = topItemByKey(navKey.slice(4))
    if (!it) return
    if (!it.closable || !cfg.system.allowClose) { openMonitor(); return }
    var st = appState[it.key] || ""
    if (st === "closing" || st === "killing") return
    if (st === "alive") {
      setAppState(it.key, "killing")
      runAct(["kill", String(it.pid), String(it.start)], function(r) { desk.finishClose(it.key, r) })
      return
    }
    if (armedKey !== navKey) {          // first Enter / click asks for confirmation
      armedKey = navKey
      armTimer.restart()
      return
    }
    armedKey = ""
    setAppState(it.key, "closing")
    runAct(["close", String(it.pid), String(it.start)], function(r) { desk.finishClose(it.key, r) })
  }
  function finishClose(k, r) {
    if (r === "alive") { setAppState(k, "alive"); return }
    setAppState(k, "")
    if (r === "error") flashRow("app:" + k, tr("cantClose"))
    else {
      topItems = topItems.filter(function(x) { return x.key !== k })
      refreshTop()
    }
  }
  function openMonitor() {
    jump(["btop"], selected, tr("cantOpen"))
  }

  // ================================================================ media
  QtObject {
    id: demoPlayer
    property string trackTitle: "Neon Drift"
    property string trackArtist: "Analog Hearts"
    property string trackArtUrl: Qt.resolvedUrl("assets/demo-cover.png")
    property string identity: "Spotify"
    property string dbusName: "demo"
    property string desktopEntry: ""
    property bool isPlaying: true
    property real position: 102
    property real length: 245
    property bool lengthSupported: true
    property bool canGoNext: true
    property bool canGoPrevious: true
    property bool canTogglePlaying: true
    property bool canRaise: false
    function togglePlaying() { isPlaying = !isPlaying }
    function next() { position = 0 }
    function previous() { position = 0 }
  }
  Timer {
    interval: 1000
    repeat: true
    running: desk.demo && demoPlayer.isPlaying
    onTriggered: demoPlayer.position = (demoPlayer.position + 1) % demoPlayer.length
  }

  readonly property var mprisList: {
    if (demo) return [demoPlayer]
    var src = Mpris.players ? Mpris.players.values : []
    var out = []
    for (var i = 0; i < src.length; i++) {
      var p = src[i]
      if (p && (p.trackTitle || p.trackArtist)) out.push(p)
    }
    return out
  }
  property var playStarts: ({})        // dbusName -> when it started playing
  property string pinnedName: ""       // picked by hand with [ ] or ↑↓
  property double pinnedAt: 0

  function markStart(name) {
    var p = Object.assign({}, playStarts)
    p[name] = Date.now()
    playStarts = p
  }
  Variants {
    model: Mpris.players ? Mpris.players.values : []
    delegate: QtObject {
      required property var modelData
      readonly property bool playing: !!modelData && modelData.isPlaying
      onPlayingChanged: if (playing) desk.markStart(modelData.dbusName)
      Component.onCompleted: if (playing) desk.markStart(modelData.dbusName)
    }
  }

  // The last thing that started playing wins; a source picked by hand is
  // kept until something else starts playing.
  readonly property var player: {
    var list = mprisList
    if (!list.length) return null
    var best = null, bestT = -1
    for (var i = 0; i < list.length; i++) {
      if (!list[i].isPlaying) continue
      var t = playStarts[list[i].dbusName] || 0
      if (t > bestT) { best = list[i]; bestT = t }
    }
    var pinned = null
    for (var j = 0; j < list.length; j++) if (list[j].dbusName === pinnedName) pinned = list[j]
    if (pinned && (!best || pinnedAt >= bestT)) return pinned
    if (best) return best
    var recent = list[0], rt = -1
    for (var k = 0; k < list.length; k++) {
      var t2 = playStarts[list[k].dbusName] || 0
      if (t2 > rt) { recent = list[k]; rt = t2 }
    }
    return recent
  }
  readonly property int playerIndex: player ? mprisList.indexOf(player) : -1
  readonly property bool mediaVisible: shown("media") && player !== null
    && (!cfg.media.hideWhenPaused || player.isPlaying)

  function cyclePlayer(d) {
    var n = mprisList.length
    if (n < 2) return
    var i = ((playerIndex < 0 ? 0 : playerIndex) + d + n) % n
    pinnedName = mprisList[i].dbusName
    pinnedAt = Date.now()
    bump()
  }
  function openPlayer() {
    var p = player
    if (!p || demo) return
    // The Omarchy Spotify plugin has no window: its player opens over IPC.
    if (p.desktopEntry === "omarchy-spotify" || String(p.identity || "").indexOf("Omarchy Spotify") === 0) {
      afterJump()
      Quickshell.execDetached(["omarchy-shell", "-q", "quickshell.spotify.player", "toggleFullPlayer"])
      return
    }
    if (p.canRaise) p.raise()
    jump(["focus-bus", p.dbusName, p.desktopEntry || ""], "media", tr("noPlayerWindow"))
  }

  // MPRIS does not update the position on its own: ask for it.
  Timer {
    interval: 1000
    repeat: true
    running: !desk.demo && desk.player !== null && desk.player.isPlaying && desk.anyDesktopVisible
    onTriggered: if (desk.player) desk.player.positionChanged()
  }

  // ================================================================ layout
  readonly property var cardOrder: ["clock", "agents", "media", "system"]
  function slotCards(slot) {
    var out = []
    for (var i = 0; i < cardOrder.length; i++) if (cfg[cardOrder[i]].position === slot) out.push(cardOrder[i])
    return out
  }
  function zoneX(slot) { return slot.indexOf("left") >= 0 ? 0 : (slot.indexOf("right") >= 0 ? 2 : 1) }
  function zoneY(slot) { return slot.indexOf("top") === 0 ? 0 : (slot === "center" ? 1 : 2) }

  // ================================================================ navigation
  // Three columns (left | center | right). ←→ changes column, ↑↓ moves inside.
  property string selected: ""
  property bool keyboardNav: false
  property var selectedPos: null
  property var lastIndex: [0, 0, 0]

  readonly property var agentKeys: {
    var out = []
    if (!agentsActive) return out
    for (var i = 0; i < groups.length; i++) {
      var ag = groups[i].agents
      for (var j = 0; j < Math.min(ag.length, cfg.agents.maxPerGroup); j++) out.push("agent:" + ag[j].key)
    }
    return out
  }
  readonly property var appKeys: {
    var out = []
    for (var i = 0; i < topItems.length; i++) out.push("app:" + topItems[i].key)
    out.push("sys:monitor")
    return out
  }
  // Rows of the System card, in order, with what is actually available.
  readonly property var systemRows: {
    var out = []
    var rows = cfg.system.rows
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i]
      if (r === "gpu" && !gpu) continue
      if (r === "vram" && !(gpu && gpu.state === "active" && gpu.vramTotal > 0)) continue
      if (r === "fans" && fans.length === 0) continue
      if (r === "battery" && !battery) continue
      if (r === "net" && rxRate < 0) continue
      if (r === "disk") {
        for (var d = 0; d < disks.length; d++) out.push("disk:" + d)
        continue
      }
      out.push(r)
    }
    return out
  }
  readonly property var systemKeys: {
    if (!systemActive || !sysReady) return []
    var out = []
    for (var i = 0; i < systemRows.length; i++) {
      var r = systemRows[i]
      out.push("sys:" + r)
      if ((r === "cpu" || r === "ram") && expanded === r) out = out.concat(appKeys)
    }
    return out
  }
  function keysFor(card) {
    if (card === "agents") return agentKeys
    if (card === "media") return mediaVisible ? ["media"] : []
    if (card === "system") return systemKeys
    return []
  }
  readonly property var columns: {
    var cols = [[], [], []]
    var cards = ["agents", "media", "system"].filter(function(c) { return desk.cfg[c].position !== "off" })
    cards.sort(function(a, b) {
      return (desk.zoneY(desk.cfg[a].position) - desk.zoneY(desk.cfg[b].position))
        || (desk.cardOrder.indexOf(a) - desk.cardOrder.indexOf(b))
    })
    for (var i = 0; i < cards.length; i++) {
      var z = zoneX(cfg[cards[i]].position)
      cols[z] = cols[z].concat(keysFor(cards[i]))
    }
    return cols
  }
  readonly property int navCount: columns[0].length + columns[1].length + columns[2].length
  // Is "Now playing" alone in its column? Then ↑↓ switches the source.
  readonly property bool mediaAlone: {
    var p = posOf("media")
    return !!p && columns[p[0]].length === 1
  }

  function posOf(key) {
    if (!key) return null
    for (var c = 0; c < 3; c++) {
      var i = columns[c].indexOf(key)
      if (i >= 0) return [c, i]
    }
    return null
  }
  onColumnsChanged: {
    if (!selected) return
    var p = posOf(selected)
    if (p) { selectedPos = p; return }
    // The selection disappeared: move to the closest row in the same column.
    if (selectedPos && columns[selectedPos[0]].length) {
      var col = columns[selectedPos[0]]
      selected = col[Math.min(selectedPos[1], col.length - 1)]
      return
    }
    selected = ""
  }

  function select(key, byKeyboard) {
    if (selected !== key) armedKey = ""
    selected = key
    var p = posOf(key)
    if (p) selectedPos = p
    keyboardNav = !!byKeyboard
    bump()
  }
  function hoverSelect(key) { select(key, false) }

  function selectFirst() {
    // What is waiting for you comes first.
    for (var i = 0; i < groups.length; i++)
      for (var j = 0; j < groups[i].agents.length; j++) {
        var a = groups[i].agents[j]
        if (a.state === "waiting" && agentKeys.indexOf("agent:" + a.key) >= 0) {
          select("agent:" + a.key, true)
          return
        }
      }
    for (var c = 0; c < 3; c++)
      if (columns[c].length) { select(columns[c][0], true); return }
  }

  function handleKey(e) {
    if (settingsOpen) { settingsKey(e); return }
    var k = e.key
    var vertical = k === Qt.Key_Up || k === Qt.Key_Down
    var horizontal = k === Qt.Key_Left || k === Qt.Key_Right
    if (vertical || horizontal || k === Qt.Key_Tab || k === Qt.Key_Backtab) {
      e.accepted = true
      var p = posOf(selected)
      if (!p) { selectFirst(); return }
      var c = p[0], i = p[1]
      if (k === Qt.Key_Tab || k === Qt.Key_Backtab) {
        var flat = columns[0].concat(columns[1], columns[2])
        var fi = flat.indexOf(selected) + (k === Qt.Key_Tab ? 1 : -1)
        select(flat[(fi + flat.length) % flat.length], true)
      } else if (vertical) {
        var d = k === Qt.Key_Down ? 1 : -1
        if (selected === "media" && mediaAlone) { cyclePlayer(d); keyboardNav = true; return }
        var col = columns[c]
        select(col[Math.max(0, Math.min(col.length - 1, i + d))], true)
      } else {
        var step = k === Qt.Key_Right ? 1 : -1
        var nc = c + step
        while (nc >= 0 && nc < 3 && columns[nc].length === 0) nc += step
        if (nc < 0 || nc > 2) { keyboardNav = true; bump(); return }
        var li = lastIndex.slice()
        li[c] = i
        lastIndex = li
        select(columns[nc][Math.min(li[nc] || 0, columns[nc].length - 1)], true)
      }
      return
    }
    if (k === Qt.Key_BracketLeft || k === Qt.Key_BracketRight) {
      e.accepted = true
      if (selected === "media") { cyclePlayer(k === Qt.Key_BracketRight ? 1 : -1); keyboardNav = true }
      return
    }
    if (k === Qt.Key_Return || k === Qt.Key_Enter) {
      e.accepted = true
      if (posOf(selected)) { keyboardNav = true; activate(selected, true) }
      else selectFirst()
      return
    }
    if (k === Qt.Key_Space) {
      e.accepted = true
      if (selected === "media" && player && player.canTogglePlaying) { player.togglePlaying(); bump() }
      else if (posOf(selected)) activate(selected, true)
      return
    }
    if (k === Qt.Key_Comma) {
      e.accepted = true
      openSettings()
      return
    }
    if (k === Qt.Key_Escape) {
      e.accepted = true
      if (armedKey) armedKey = ""
      else if (expanded) collapse()
      else if (summoned) dismiss()
      else { selected = ""; keyboardNav = false }
    }
  }

  function activate(key, byKeyboard) {
    bump()
    if (key.indexOf("agent:") === 0) {
      var a = agentByKey(key.slice(6))
      var t = a ? (a.target || {}) : {}
      if (t.type === "pid") jump(["focus-pid", String(t.pid)], key, tr("noWindow"))
      else if (t.type === "attach") jump(["attach", String(t.id), String(t.cwd || "")], key, tr("noWindow"))
      else if (t.type === "app") jump(["focus-app", String(t.app)], key, tr("noWindow"))
      else flashRow(key, tr("noWindow"))
    } else if (key === "media") {
      openPlayer()
    } else if (key === "sys:cpu" || key === "sys:ram") {
      toggleExpand(key.slice(4))
    } else if (key.indexOf("app:") === 0) {
      activateApp(key)
    } else if (key.indexOf("sys:") === 0) {
      openMonitor()      // GPU, disks, fans, battery, network, "open the monitor"
    }
  }
  function afterJump() {
    dismiss()
    selected = ""
    keyboardNav = false
  }

  // The selection fades on its own when nothing is touched.
  function bump() {
    idleTimer.restart()
    expandTimer.restart()
  }
  Timer {
    id: idleTimer
    interval: desk.selectionIdleMs
    onTriggered: {
      if (desk.summoned || desk.anyHover) { restart(); return }
      desk.selected = ""
      desk.keyboardNav = false
      desk.armedKey = ""
    }
  }
  Timer {
    id: expandTimer
    interval: desk.expandIdleMs
    onTriggered: {
      if (desk.summoned || desk.anyHover) { restart(); return }
      desk.collapse()
    }
  }

  // The keyboard legend at the bottom of the screen, for the selected row.
  readonly property string currentHint: {
    if (!keyboardNav || !selected || settingsOpen) return ""
    var k = selected
    var h = ""
    if (k.indexOf("agent:") === 0) h = hintFor("agents")
    else if (k === "media") h = hintFor("media")
    else if (k.indexOf("sys:") === 0 || k.indexOf("app:") === 0) h = hintFor("system")
    return h ? h + "   " + tr("hintSettings") : ""
  }
  function hintFor(section) {
    if (!keyboardNav || !selected) return ""
    var k = selected
    if (section === "agents" && k.indexOf("agent:") === 0) {
      var a = agentByKey(k.slice(6))
      var attach = a && a.target && a.target.type === "attach"
      return (attach ? tr("hintOpenSession") : tr("hintGoWindow")) + "   " + tr("hintCards")
    }
    if (section === "media" && k === "media")
      return tr("hintMedia") + (mprisList.length > 1 ? "   " + (mediaAlone ? tr("hintSwitchV") : tr("hintSwitchB")) : "")
    if (section === "system") {
      if (k === "sys:cpu" || k === "sys:ram")
        return expanded === k.slice(4) ? tr("hintCollapse") : tr("hintExpand")
      if (k.indexOf("app:") === 0) {
        var it = topItemByKey(k.slice(4))
        if (!it) return ""
        if (!it.closable || !cfg.system.allowClose) return tr("hintMonitor")
        if ((appState[it.key] || "") === "alive") return tr("hintForce")
        if (armedKey === k) return tr("hintConfirm")
        return tr("hintClose")
      }
      if (k.indexOf("sys:") === 0) return tr("hintMonitor")
    }
    return ""
  }

  // ================================================================ settings panel
  property bool settingsOpen: false
  property int settingsIndex: 0
  property bool settingsSummoned: false

  function openSettings() {
    settingsIndex = 0
    settingsOpen = true
    if (!summoned) summon()
  }
  function closeSettings() {
    settingsOpen = false
    dismiss()
  }

  readonly property var slotOptions: Settings.SLOTS.concat(["off"])
  function slotLabel(v) { return v === "off" ? tr("vHidden") : tr(v) }
  readonly property var settingsRows: [
    { key: "language", label: tr("sLanguage"), values: ["auto", "en", "es"],
      labels: [tr("vAuto"), "English", "Español"] },
    { key: "scale", label: tr("sSize"), values: [0.85, 1, 1.15, 1.3],
      labels: [tr("vSmall"), tr("vNormal"), tr("vLarge"), tr("vHuge")] },
    { key: "opacity", label: tr("sBackground"), values: [0.35, 0.62, 0.85],
      labels: [tr("vGlass"), tr("vNormal"), tr("vSolid")] },
    { key: "clock.position", label: tr("sClock"), values: slotOptions, labels: slotOptions.map(slotLabel) },
    { key: "clock.timeFormat", label: tr("sClockFormat"), values: ["HH:mm", "h:mm AP"],
      labels: [tr("v24h"), tr("v12h")] },
    { key: "agents.position", label: tr("sAgents"), values: slotOptions, labels: slotOptions.map(slotLabel) },
    { key: "media.position", label: tr("sMedia"), values: slotOptions, labels: slotOptions.map(slotLabel) },
    { key: "system.position", label: tr("sSystem"), values: slotOptions, labels: slotOptions.map(slotLabel) },
    { key: "keyboard", label: tr("sKeyboard"), values: [true, false], labels: [tr("vOn"), tr("vOff")] },
    { key: "screens", label: tr("sScreens"), values: ["all", "focused"],
      labels: [tr("vAllScreens"), tr("vFocusedScreen")] }
  ]
  function settingValueIndex(row) {
    var v = Settings.valueOf(cfg, row.key)
    for (var i = 0; i < row.values.length; i++)
      if (JSON.stringify(row.values[i]) === JSON.stringify(v)) return i
    // Not one of the presets (edited by hand): show the closest number, or nothing.
    if (typeof v === "number") {
      var best = 0
      for (var j = 1; j < row.values.length; j++)
        if (Math.abs(row.values[j] - v) < Math.abs(row.values[best] - v)) best = j
      return best
    }
    return -1
  }
  function settingLabel(row) {
    var i = settingValueIndex(row)
    return i >= 0 ? row.labels[i] : String(Settings.valueOf(cfg, row.key))
  }
  function stepSetting(index, d) {
    var row = settingsRows[index]
    if (!row) return
    var i = settingValueIndex(row)
    var n = row.values.length
    var next = i < 0 ? 0 : (i + d + n) % n
    setOption(row.key, row.values[next])
    settingsIndex = index
    bump()
  }
  function settingsKey(e) {
    var k = e.key
    e.accepted = true
    if (k === Qt.Key_Up || k === Qt.Key_Backtab) settingsIndex = Math.max(0, settingsIndex - 1)
    else if (k === Qt.Key_Down || k === Qt.Key_Tab) settingsIndex = Math.min(settingsRows.length - 1, settingsIndex + 1)
    else if (k === Qt.Key_Left) stepSetting(settingsIndex, -1)
    else if (k === Qt.Key_Right || k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Space) stepSetting(settingsIndex, 1)
    else if (k === Qt.Key_Escape || k === Qt.Key_Comma) closeSettings()
    else e.accepted = false
    bump()
  }

  // ================================================================ windows
  function screenAllowed(scr) {
    var sc = cfg.screens
    if (!Array.isArray(sc)) return true
    return sc.indexOf(scr.name) >= 0
  }
  readonly property var windowScreens: {
    var list = Quickshell.screens
    var out = []
    for (var i = 0; i < list.length; i++) if (screenAllowed(list[i])) out.push(list[i])
    return out
  }

  Variants {
    model: desk.windowScreens

    PanelWindow {
      id: win
      required property var modelData

      screen: modelData
      color: "transparent"
      anchors { top: true; bottom: true; left: true; right: true }
      // Normal with a zero zone = respects the bar.
      exclusionMode: ExclusionMode.Normal
      exclusiveZone: 0

      readonly property var hmon: Hyprland.monitorFor(modelData)
      readonly property string monName: hmon ? hmon.name : ""
      readonly property bool isSummoned: desk.summoned
        && (desk.summonMonitor === monName || desk.summonMonitor === "")
      readonly property int wsWindows: hmon && hmon.activeWorkspace
        ? hmon.activeWorkspace.toplevels.values.length : -1
      // The cards show on this screen (all screens, or only the focused one).
      readonly property bool cardsHere: desk.cfg.screens !== "focused" || isSummoned || (!!hmon && hmon.focused)
      // Empty desktop, on the focused monitor and without a special workspace on top.
      readonly property bool deskActive: desk.cfg.keyboard && desk.hyprReady && wsWindows === 0
        && !!hmon && hmon.focused && !desk.specialOn[monName] && desk.navCount > 0
      readonly property bool fullInput: isSummoned || deskActive
      property bool pulsing: false

      WlrLayershell.namespace: "eyemarchy"
      WlrLayershell.layer: isSummoned ? WlrLayer.Overlay : WlrLayer.Bottom
      // To get keys on an empty desktop the layer asks for the keyboard for an
      // instant (Exclusive) and then stays "on demand": any new window takes it
      // back by itself. While jumping to another window it lets go entirely:
      // with an Exclusive layer Hyprland would not focus that window.
      readonly property int focusMode: desk.actionPending || desk.previewOnly ? WlrKeyboardFocus.None
        : ((isSummoned || pulsing) ? WlrKeyboardFocus.Exclusive
          : (deskActive ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None))
      WlrLayershell.keyboardFocus: focusMode

      // The window respects the bar; the center slot uses the whole screen.
      readonly property real insetX: desk.barPosition === "left" ? Math.max(0, modelData.width - width) : 0
      readonly property real insetY: desk.barPosition === "top" ? Math.max(0, modelData.height - height) : 0

      onDeskActiveChanged: {
        if (deskActive) kickDelay.restart()
        else kickDelay.stop()
      }
      onIsSummonedChanged: if (isSummoned) keySink.forceActiveFocus()

      Timer { id: kickDelay; interval: 160; onTriggered: if (win.deskActive) desk.requestKick() }
      Timer { id: pulseEnd; interval: 120; onTriggered: win.pulsing = false }
      Connections {
        target: desk
        function onKickWanted() { if (win.deskActive) kickDelay.restart() }
        function onKickApproved() {
          if (!win.deskActive || win.isSummoned) return
          win.pulsing = true
          pulseEnd.restart()
          keySink.forceActiveFocus()
        }
      }

      Component.onCompleted: desk.wins = desk.wins.concat([win])
      Component.onDestruction: desk.wins = desk.wins.filter(function(x) { return x !== win })

      // Mouse: on an empty desktop or when summoned, the whole screen; otherwise only the cards.
      mask: Region {
        item: win.fullInput ? backdrop : null
        Region { item: !win.fullInput && sTL.interactive ? sTL : null }
        Region { item: !win.fullInput && sTC.interactive ? sTC : null }
        Region { item: !win.fullInput && sTR.interactive ? sTR : null }
        Region { item: !win.fullInput && sC.interactive ? sC : null }
        Region { item: !win.fullInput && sBL.interactive ? sBL : null }
        Region { item: !win.fullInput && sBC.interactive ? sBC : null }
        Region { item: !win.fullInput && sBR.interactive ? sBR : null }
      }

      // Dimmed background when summoned over windows; click outside to leave.
      Rectangle {
        id: backdrop
        anchors.fill: parent
        color: Util.alpha(Color.background, 0.72)
        opacity: win.isSummoned ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        MouseArea {
          anchors.fill: parent
          enabled: win.isSummoned
          onClicked: desk.settingsOpen ? desk.closeSettings() : desk.dismiss()
        }
      }

      readonly property bool hasKeys: keySink.activeFocus

      Item {
        id: keySink
        anchors.fill: parent
        focus: true
        Keys.onPressed: (event) => desk.handleKey(event)
      }

      // ---- the cards, one Column per slot ---------------------------------
      component CardSlot: Column {
        id: slotCol
        required property string slot
        readonly property var cards: desk.slotCards(slot)
        readonly property int zx: desk.zoneX(slot)
        readonly property bool interactive: visible && cards.some(function(c) { return c !== "clock" })
        readonly property real anchorHeight: rep.count > 0 && rep.itemAt(0) ? rep.itemAt(0).height : 0

        visible: cards.length > 0 && win.cardsHere && !(desk.settingsOpen && win.isSummoned)
        spacing: desk.px(slot === "center" ? 28 : 16)

        x: zx === 0 ? desk.margin
          : (zx === 2 ? win.width - width - desk.margin
            : Math.round((win.modelData.width - width) / 2 - win.insetX))
        y: slot.indexOf("top") === 0 ? desk.margin
          : (slot === "center"
            ? Math.round(win.modelData.height / 2 + desk.cfg.clock.offset * desk.s - anchorHeight / 2 - win.insetY)
            : win.height - height - desk.margin)

        Repeater {
          id: rep
          model: slotCol.cards
          delegate: Loader {
            required property string modelData
            anchors.left: slotCol.zx === 0 ? parent.left : undefined
            anchors.right: slotCol.zx === 2 ? parent.right : undefined
            anchors.horizontalCenter: slotCol.zx === 1 ? parent.horizontalCenter : undefined
            sourceComponent: modelData === "clock" ? clockComp
              : modelData === "agents" ? agentsComp
              : modelData === "media" ? mediaComp : systemComp
          }
        }
      }

      Component { id: clockComp; ClockCard { host: desk } }
      Component { id: agentsComp; AgentsCard { host: desk } }
      Component { id: mediaComp; MediaCard { host: desk } }
      Component { id: systemComp; SystemCard { host: desk } }

      CardSlot { id: sTL; slot: "top-left" }
      CardSlot { id: sTC; slot: "top-center" }
      CardSlot { id: sTR; slot: "top-right" }
      CardSlot { id: sC; slot: "center" }
      CardSlot { id: sBL; slot: "bottom-left" }
      CardSlot { id: sBC; slot: "bottom-center" }
      CardSlot { id: sBR; slot: "bottom-right" }

      SettingsCard {
        host: desk
        anchors.centerIn: parent
        opacity: desk.settingsOpen && win.isSummoned ? 1 : 0
      }

      Hint {
        host: desk
        text: win.cardsHere && (win.deskActive || win.isSummoned) ? desk.currentHint : ""
        x: Math.round((win.modelData.width - width) / 2 - win.insetX)
        y: sBC.visible ? sBC.y - height - desk.px(12) : win.height - height - desk.margin
      }
    }
  }
}
