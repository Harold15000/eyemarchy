import QtQuick
import qs.Commons

// Keyboard hint ("↵ go to its window") in a tag under a card.
// Only shown while navigating with the arrows.
Rectangle {
  id: hint

  required property var host
  property string text: ""

  height: host.px(22)
  width: label.implicitWidth + host.px(20)
  radius: Style.cornerRadius
  color: Util.alpha(Color.background, host.backgroundAlpha)
  border.width: 1
  border.color: Util.alpha(Color.foreground, 0.10)
  visible: opacity > 0
  opacity: text !== "" ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 160 } }

  Text {
    id: label
    anchors.centerIn: parent
    text: hint.text
    color: Util.alpha(Color.foreground, 0.7)
    font.family: Style.fontFamily
    font.pixelSize: hint.host.px(10)
    font.letterSpacing: 1
  }
}
