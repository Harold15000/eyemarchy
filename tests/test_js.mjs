// Tests for the QML-side JavaScript libraries (Settings.js, I18n.js, Demo.js).
// Run with: node --test tests/
import { test } from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"
import vm from "node:vm"

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..")

// QML JavaScript libraries start with ".pragma library": drop it and run the
// rest in a sandbox, then read the top-level declarations back.
function load(file) {
  const src = readFileSync(path.join(root, file), "utf8").replace(/^\.pragma library\s*$/m, "")
  const ctx = {}
  vm.createContext(ctx)
  vm.runInContext(src + "\n;globalThis.__lib = this", ctx)
  return ctx
}

// Objects made inside the sandbox have their own prototypes: compare plain copies.
const plain = (v) => JSON.parse(JSON.stringify(v))

const Settings = load("Settings.js")
const I18n = load("I18n.js")
const Demo = load("Demo.js")

test("defaults survive normalize unchanged", () => {
  const cfg = Settings.normalize({})
  assert.equal(cfg.scale, 1)
  assert.equal(cfg.clock.position, "center")
  assert.equal(cfg.agents.position, "top-left")
  assert.deepEqual(plain(cfg.system.rows), plain(Settings.SYSTEM_ROWS))
  assert.deepEqual(plain(Settings.diff(cfg)), {})
})

test("bad values fall back or clamp", () => {
  const cfg = Settings.normalize({
    scale: 9, opacity: "x", language: "klingon", screens: 3,
    clock: { position: "somewhere", size: -5 },
    agents: { maxPerGroup: 0, custom: [{ name: "ok", match: "a" }, { name: 1 }, "nope"] },
    system: { rows: ["cpu", "bogus", "cpu"], warnPercent: 500 }
  })
  assert.equal(cfg.scale, 1.6)
  assert.equal(cfg.opacity, Settings.DEFAULTS.opacity)
  assert.equal(cfg.language, "auto")
  assert.equal(cfg.screens, "all")
  assert.equal(cfg.clock.position, "center")
  assert.equal(cfg.clock.size, 40)
  assert.equal(cfg.agents.maxPerGroup, 1)
  assert.equal(cfg.agents.custom.length, 1)
  assert.deepEqual(plain(cfg.system.rows), ["cpu"])
  assert.equal(cfg.system.warnPercent, 100)
})

test("screens accepts a list of outputs", () => {
  assert.deepEqual(plain(Settings.normalize({ screens: ["DP-1", "DP-1", "eDP-1"] }).screens), ["DP-1", "eDP-1"])
  assert.equal(Settings.normalize({ screens: "focused" }).screens, "focused")
  assert.equal(Settings.normalize({ screens: [] }).screens, "all")
})

test("diff writes only what changed", () => {
  let cfg = Settings.normalize({})
  cfg = Settings.withValue(cfg, "agents.position", "top-right")
  cfg = Settings.withValue(cfg, "scale", 1.15)
  assert.deepEqual(plain(Settings.diff(cfg)), { scale: 1.15, agents: { position: "top-right" } })
  cfg = Settings.withValue(cfg, "scale", 1)
  assert.deepEqual(plain(Settings.diff(cfg)), { agents: { position: "top-right" } })
})

test("valueOf reads dotted keys", () => {
  const cfg = Settings.normalize({ media: { position: "off" } })
  assert.equal(Settings.valueOf(cfg, "media.position"), "off")
  assert.equal(Settings.valueOf(cfg, "nope.deeper"), undefined)
})

test("every language has every English key", () => {
  const en = Object.keys(I18n.STRINGS.en)
  for (const lang of I18n.LANGUAGES) {
    const missing = en.filter(k => !(k in I18n.STRINGS[lang]) && !["cpu", "ram", "gpu", "vram", "home", "demo"].includes(k))
    assert.deepEqual(plain(missing), [], `${lang} is missing ${missing.join(", ")}`)
  }
})

test("placeholders are kept in translations", () => {
  for (const lang of I18n.LANGUAGES) {
    for (const [k, v] of Object.entries(I18n.STRINGS.en)) {
      const t = I18n.STRINGS[lang][k]
      if (t === undefined) continue
      for (const ph of ["%1", "%2"]) assert.equal(v.includes(ph), t.includes(ph), `${lang}.${k} ${ph}`)
    }
  }
})

test("language resolution", () => {
  assert.equal(I18n.resolve("auto", "es_ES", "es_ES.UTF-8"), "es")
  assert.equal(I18n.resolve("auto", "de_DE", "de_DE.UTF-8"), "en")
  assert.equal(I18n.resolve("es", "en_US", "en_US.UTF-8"), "es")
  assert.equal(I18n.resolve("auto", "C", ""), "en")
  assert.equal(I18n.tr("es", "working", "3m"), "trabajando · 3m")
  assert.equal(I18n.tr("es", "cpu"), "CPU")
  assert.equal(I18n.tr("xx", "calm"), "all quiet")
})

test("demo data has the shape the cards expect", () => {
  const groups = Demo.groups(Date.now())
  assert.ok(groups.length >= 3)
  for (const g of groups) {
    assert.ok(g.id && g.label && Array.isArray(g.agents))
    for (const a of g.agents) assert.ok(["working", "waiting", "idle"].includes(a.state))
  }
  assert.ok(Demo.top("cpu").some(i => i.detailCode === "system"))
})
