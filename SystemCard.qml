import QtQuick
import qs.Commons

// "System". CPU and RAM unfold into the apps that use them most; the other
// rows open btop. Rows the machine does not have (no GPU, no battery) are left out.
CardFrame {
  id: card

  readonly property var sys: host.cfg.system

  width: host.panelWidth
  height: content.implicitHeight + host.px(36)
  opacity: host.shown("system") && host.sysReady ? 1 : 0
  Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

  HoverHandler { onHoveredChanged: card.host.setHover("system", hovered) }

  function pct(used, total) { return total > 0 ? 100 * used / total : 0 }

  // Row: label, value, detail on the right and a thin bar.
  component StatRow: Item {
    id: row
    property string navKey: ""
    property string label: ""
    property string value: ""
    property string detail: ""
    property real percent: -1          // -1 = no bar
    property bool warn: false
    property bool dim: false
    property bool expandable: false
    readonly property bool expanded: expandable && card.host.expanded === navKey.slice(4)
    readonly property bool selected: card.host.selected === navKey

    width: parent ? parent.width : 0
    height: inner.implicitHeight

    NavRow { host: card.host; navKey: row.navKey }

    Column {
      id: inner
      width: parent.width
      spacing: card.host.px(5)

      Item {
        width: parent.width
        height: labelText.implicitHeight

        Text {
          id: labelText
          anchors.left: parent.left
          text: row.label
          color: Util.alpha(Color.foreground, 0.72)
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(11)
          font.letterSpacing: 2
        }
        // Arrow: the row unfolds.
        Text {
          visible: row.expandable
          anchors.left: labelText.right
          anchors.leftMargin: card.host.px(4)
          anchors.verticalCenter: labelText.verticalCenter
          text: row.expanded ? "󰅀" : "󰅂"
          color: row.expanded || row.selected ? Color.accent : Util.alpha(Color.foreground, 0.35)
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(11)
        }
        Text {
          anchors.right: parent.right
          anchors.baseline: labelText.baseline
          text: row.value + (row.detail ? "   " + row.detail : "")
          color: row.warn ? Color.urgent : Util.alpha(Color.foreground, row.dim ? 0.5 : 0.95)
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(12)
          font.weight: Font.Medium
        }
      }

      Rectangle {
        visible: row.percent >= 0
        width: parent.width
        height: Math.max(2, card.host.px(3))
        radius: height / 2
        color: Util.alpha(Color.foreground, 0.12)

        Rectangle {
          width: parent.width * Math.max(0, Math.min(1, row.percent / 100))
          height: parent.height
          radius: parent.radius
          color: row.warn ? Color.urgent : Color.accent
          Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
          Behavior on color { ColorAnimation { duration: 400 } }
        }
      }
    }
  }

  // An app in the unfolded list.
  component AppRow: Item {
    id: arow
    required property var item
    property real maxValue: 1
    readonly property string navKey: "app:" + item.key
    readonly property string st: card.host.appState[item.key] || ""
    readonly property bool armed: card.host.armedKey === navKey
    readonly property string flashText: card.host.flash[navKey] || ""
    readonly property bool canClose: item.closable && card.sys.allowClose
    readonly property string rightText: {
      if (flashText) return flashText
      if (st === "closing") return card.host.tr("closing")
      if (st === "killing") return card.host.tr("forcing")
      if (st === "alive") return card.host.tr("notResponding")
      if (armed) return card.host.tr("askClose", card.host.keyboardNav ? "↵" : card.host.tr("click"))
      return item.text
    }
    readonly property bool alert: armed || st === "alive" || flashText !== ""

    width: parent ? parent.width : 0
    height: card.host.px(28)

    NavRow { host: card.host; navKey: arow.navKey; padY: card.host.px(2) }

    Text {
      id: appName
      anchors.left: parent.left
      anchors.top: parent.top
      anchors.topMargin: card.host.px(3)
      width: Math.min(implicitWidth, parent.width * 0.55)
      text: card.host.topItemName(arow.item)
      color: Util.alpha(Color.foreground, arow.canClose ? 0.92 : 0.7)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(12)
      elide: Text.ElideRight
    }
    Text {
      anchors.left: appName.right
      anchors.leftMargin: card.host.px(7)
      anchors.right: valueText.left
      anchors.rightMargin: card.host.px(8)
      anchors.baseline: appName.baseline
      text: card.host.topItemDetail(arow.item)
      color: Util.alpha(Color.foreground, 0.42)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(10)
      elide: Text.ElideRight
    }
    Text {
      id: valueText
      anchors.right: parent.right
      anchors.baseline: appName.baseline
      text: arow.rightText
      color: arow.alert ? Color.urgent : Util.alpha(Color.foreground, arow.st ? 0.55 : 0.9)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(11)
      font.weight: Font.Medium
    }
    // Bar relative to the heaviest app.
    Rectangle {
      anchors.left: parent.left
      anchors.bottom: parent.bottom
      anchors.bottomMargin: card.host.px(3)
      height: 2
      radius: 1
      width: parent.width * Math.max(0.02, Math.min(1, arow.item.value / Math.max(arow.maxValue, 1e-9)))
      color: arow.alert ? Color.urgent : Util.alpha(Color.accent, 0.6)
      Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
    }
  }

  component AppList: Column {
    id: list
    property string mode: ""
    readonly property bool open: card.host.expanded === mode
    readonly property real maxValue: {
      var m = 0
      var items = card.host.topItems
      for (var i = 0; i < items.length; i++) m = Math.max(m, items[i].value)
      return m
    }
    visible: open
    x: card.host.px(12)
    width: parent ? parent.width - card.host.px(12) : 0
    spacing: 2
    topPadding: 2

    Text {
      visible: list.open && card.host.topItems.length === 0
      text: card.host.tr("measuring")
      color: Util.alpha(Color.foreground, 0.45)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(11)
      height: card.host.px(24)
      verticalAlignment: Text.AlignVCenter
    }

    Repeater {
      model: list.open ? card.host.topItems : []
      delegate: AppRow {
        required property var modelData
        item: modelData
        maxValue: list.maxValue
      }
    }

    Item {
      width: parent.width
      height: card.host.px(24)
      NavRow { host: card.host; navKey: "sys:monitor"; padY: card.host.px(2) }
      Text {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: card.host.tr("openMonitor")
        color: Util.alpha(Color.foreground, card.host.selected === "sys:monitor" ? 0.95 : 0.6)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(11)
      }
      Text {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "btop 󰁔"
        color: Util.alpha(Color.foreground, 0.4)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(11)
      }
    }
  }

  // One row for each id in host.systemRows ("cpu", "disk:0", ...).
  component SystemRow: Column {
    id: srow
    required property string rowId
    readonly property var h: card.host
    readonly property string kind: rowId.split(":")[0]
    readonly property var diskInfo: kind === "disk" ? h.disks[Number(rowId.split(":")[1])] : null
    readonly property var g: h.gpu
    readonly property bool gpuAwake: !!g && g.state === "active"
    width: parent ? parent.width : 0
    spacing: card.host.px(13)

    StatRow {
      navKey: "sys:" + srow.rowId
      expandable: srow.kind === "cpu" || srow.kind === "ram"
      label: {
        switch (srow.kind) {
          case "disk": return srow.diskInfo && srow.diskInfo.mount !== "/"
            ? (srow.diskInfo.mount === "/home" ? srow.h.tr("home") : srow.diskInfo.mount.split("/").pop().toUpperCase())
            : srow.h.tr("disk")
          case "gpu": return srow.h.tr("gpu") + (srow.g && srow.g.name && srow.g.name !== "NVIDIA" && srow.g.name !== "AMD" ? " · " + srow.g.name : "")
          default: return srow.h.tr(srow.kind)
        }
      }
      value: {
        switch (srow.kind) {
          case "cpu": return Math.round(srow.h.cpuPct) + "%"
          case "ram": return srow.h.gb(srow.h.memUsed) + " / " + srow.h.gb(srow.h.memTotal) + " GB"
          case "gpu": return srow.gpuAwake ? Math.round(srow.g.util) + "%" : srow.h.tr("asleep")
          case "vram": return srow.gpuAwake ? srow.h.gb(srow.g.vramUsed) + " / " + srow.h.gb(srow.g.vramTotal) + " GB" : ""
          case "disk": return srow.diskInfo ? srow.h.gb(srow.diskInfo.used) + " / " + srow.h.gb(srow.diskInfo.total) + " GB" : ""
          case "fans": return srow.h.fans.join(" · ") + " RPM"
          case "battery": return srow.h.battery ? srow.h.battery.percent + "%" : ""
          case "net": return "↓ " + srow.h.rate(srow.h.rxRate) + "   ↑ " + srow.h.rate(srow.h.txRate)
        }
        return ""
      }
      detail: {
        switch (srow.kind) {
          case "cpu": return srow.h.cpuTemp > 0 ? Math.round(srow.h.cpuTemp) + "°" : ""
          case "gpu": return srow.gpuAwake && srow.g.temp ? Math.round(srow.g.temp) + "°" : ""
          case "battery": {
            var st = srow.h.battery ? srow.h.battery.status : ""
            return st === "charging" ? srow.h.tr("charging") : st === "discharging" ? srow.h.tr("discharging")
              : st === "full" ? srow.h.tr("full") : st ? srow.h.tr("plugged") : ""
          }
        }
        return ""
      }
      percent: {
        switch (srow.kind) {
          case "cpu": return srow.h.cpuPct
          case "ram": return card.pct(srow.h.memUsed, srow.h.memTotal)
          case "gpu": return srow.gpuAwake ? srow.g.util : 0
          case "vram": return srow.gpuAwake ? card.pct(srow.g.vramUsed, srow.g.vramTotal) : 0
          case "disk": return srow.diskInfo ? card.pct(srow.diskInfo.used, srow.diskInfo.total) : 0
          case "battery": return srow.h.battery ? srow.h.battery.percent : 0
        }
        return -1
      }
      dim: srow.kind === "gpu" && !srow.gpuAwake
      warn: {
        var w = card.sys.warnPercent, t = card.sys.warnTemp
        switch (srow.kind) {
          case "cpu": return srow.h.cpuPct >= w || srow.h.cpuTemp >= t
          case "ram": return card.pct(srow.h.memUsed, srow.h.memTotal) >= w
          case "gpu": return srow.gpuAwake && (srow.g.util >= w || (srow.g.temp || 0) >= t)
          case "vram": return srow.gpuAwake && card.pct(srow.g.vramUsed, srow.g.vramTotal) >= w
          case "disk": return !!srow.diskInfo && card.pct(srow.diskInfo.used, srow.diskInfo.total) >= Math.max(w, 90)
          case "battery": return !!srow.h.battery && srow.h.battery.status === "discharging" && srow.h.battery.percent <= 15
        }
        return false
      }
    }

    AppList { mode: srow.kind; visible: open && (srow.kind === "cpu" || srow.kind === "ram") }
  }

  Column {
    id: content
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.margins: card.host.px(18)
    spacing: card.host.px(13)

    Item {
      width: parent.width
      height: sysTitle.implicitHeight

      Row {
        spacing: card.host.px(8)
        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: card.host.px(6); height: width; radius: width / 2
          color: Color.accent
        }
        Text {
          id: sysTitle
          text: card.host.tr("system")
          color: Color.foreground
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(12)
          font.weight: Font.DemiBold
          font.letterSpacing: 4
        }
      }
      Text {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        visible: card.host.expanded !== ""
        text: card.host.tr("byApp")
        color: Util.alpha(Color.foreground, 0.45)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(11)
      }
    }

    Repeater {
      model: card.host.systemRows
      delegate: SystemRow {
        required property string modelData
        rowId: modelData
      }
    }
  }
}
