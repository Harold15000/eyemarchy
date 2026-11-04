import QtQuick
import qs.Commons

// The frame every card shares: theme background, hairline border, fades.
// With `alert` set (an agent is waiting for you) the border breathes.
Rectangle {
  id: frame

  required property var host
  property bool alert: false
  property real glow: 0

  radius: Style.cornerRadius
  color: Util.alpha(Color.background, host.backgroundAlpha)
  border.width: 1
  border.color: alert ? Util.alpha(Color.urgent, 0.35 + 0.45 * glow) : Util.alpha(Color.foreground, 0.10)
  visible: opacity > 0

  Behavior on opacity { NumberAnimation { duration: 400 } }
  Behavior on color { ColorAnimation { duration: 400 } }

  SequentialAnimation on glow {
    running: frame.alert && frame.visible
    loops: Animation.Infinite
    NumberAnimation { from: 0; to: 1; duration: 1200; easing.type: Easing.InOutSine }
    NumberAnimation { from: 1; to: 0; duration: 1200; easing.type: Easing.InOutSine }
  }
}
