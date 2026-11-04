import QtQuick
import qs.Commons

// Selection background + mouse handling for a navigable row. Put it first in
// the row: it sits behind the text, and since text takes no clicks, the
// MouseArea still gets them.
Item {
  id: nav

  required property var host
  required property string navKey
  property real padX: host.px(10)
  property real padY: host.px(4)

  readonly property bool selected: host.selected === navKey
  readonly property bool hovered: mouse.containsMouse

  anchors.fill: parent

  Rectangle {
    anchors.fill: parent
    anchors.leftMargin: -nav.padX
    anchors.rightMargin: -nav.padX
    anchors.topMargin: -nav.padY
    anchors.bottomMargin: -nav.padY
    radius: Style.cornerRadius
    color: Util.alpha(Color.accent, nav.selected ? 0.14 : (nav.hovered ? 0.07 : 0))
    Behavior on color { ColorAnimation { duration: 140 } }

    Rectangle {
      anchors.left: parent.left
      anchors.top: parent.top
      anchors.bottom: parent.bottom
      width: 2
      color: Color.accent
      opacity: nav.selected ? 1 : 0
      Behavior on opacity { NumberAnimation { duration: 140 } }
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    anchors.leftMargin: -nav.padX
    anchors.rightMargin: -nav.padX
    anchors.topMargin: -nav.padY
    anchors.bottomMargin: -nav.padY
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onEntered: nav.host.hoverSelect(nav.navKey)
    onClicked: nav.host.activate(nav.navKey, false)
  }
}
