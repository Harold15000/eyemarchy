import Quickshell
import QtQuick
import QtQuick.Effects
import qs.Commons

// Big clock and date, in the theme's colours, with a soft shadow so it reads
// on any wallpaper. Takes no clicks.
Item {
  id: root

  required property var host
  readonly property var cfg: host.cfg.clock

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  visible: opacity > 0
  opacity: host.shown("clock") ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 400 } }

  SystemClock {
    id: clock
    precision: root.cfg.timeFormat.indexOf("s") >= 0 ? SystemClock.Seconds : SystemClock.Minutes
  }

  MultiEffect {
    source: column
    anchors.fill: column
    autoPaddingEnabled: true
    shadowEnabled: true
    shadowColor: Color.background
    shadowOpacity: 1.0
    blurMax: 48
    shadowBlur: 0.8
    shadowScale: 1.02
    shadowVerticalOffset: 3
    shadowHorizontalOffset: 0
  }

  Column {
    id: column
    anchors.centerIn: parent
    spacing: root.host.px(6)
    // Drawn through the MultiEffect above.
    visible: false
    layer.enabled: true

    Text {
      id: timeText
      anchors.horizontalCenter: parent.horizontalCenter
      text: root.host.locale.toString(clock.date, root.cfg.timeFormat)
      color: Color.foreground
      font.family: Style.fontFamily
      font.pixelSize: Math.round(root.cfg.size * root.host.s)
      font.weight: Font.Light
      font.letterSpacing: -2
      renderType: Text.QtRendering
      Behavior on color { ColorAnimation { duration: 400 } }
    }

    // Accent line from the theme.
    Rectangle {
      anchors.horizontalCenter: parent.horizontalCenter
      width: Math.max(root.host.px(48), timeText.implicitWidth * 0.18)
      height: Math.max(2, root.host.px(3))
      radius: height / 2
      color: Color.accent
      Behavior on color { ColorAnimation { duration: 400 } }
    }

    Item { width: 1; height: root.host.px(4); visible: root.cfg.showDate }

    Text {
      visible: root.cfg.showDate
      anchors.horizontalCenter: parent.horizontalCenter
      text: root.host.locale.toString(clock.date, root.cfg.dateFormat || root.host.tr("dateFormat")).toUpperCase()
      color: Util.alpha(Color.foreground, 0.9)
      font.family: Style.fontFamily
      font.pixelSize: Math.round(root.cfg.size * 0.13 * root.host.s)
      font.weight: Font.Medium
      font.letterSpacing: 5
      renderType: Text.QtRendering
      Behavior on color { ColorAnimation { duration: 400 } }
    }
  }
}
