import QtQuick
import qs.Commons

// Settings, summoned with `omarchy-shell eyemarchy settings` or "," on the
// desktop. ↑↓ choose, ←→ (or a click) change, Esc closes. Every change is
// saved at once in the plugin's entry in ~/.config/omarchy/shell.json.
CardFrame {
  id: card

  width: host.px(460)
  height: content.implicitHeight + host.px(40)
  color: Util.alpha(Color.background, 0.97)
  border.color: Util.alpha(Color.accent, 0.35)

  HoverHandler { onHoveredChanged: card.host.setHover("settings", hovered) }

  // Clicks inside the card must not reach the backdrop (which closes it).
  MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

  Column {
    id: content
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.margins: card.host.px(20)
    spacing: card.host.px(6)

    Row {
      spacing: card.host.px(8)
      bottomPadding: card.host.px(10)
      Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: card.host.px(6); height: width; radius: width / 2
        color: Color.accent
      }
      Text {
        text: card.host.tr("settings")
        color: Color.foreground
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(12)
        font.weight: Font.DemiBold
        font.letterSpacing: 4
      }
    }

    Repeater {
      model: card.host.settingsRows

      delegate: Item {
        id: row
        required property var modelData
        required property int index
        readonly property bool selected: card.host.settingsIndex === index

        width: content.width
        height: card.host.px(30)

        Rectangle {
          anchors.fill: parent
          anchors.leftMargin: -card.host.px(8)
          anchors.rightMargin: -card.host.px(8)
          radius: Style.cornerRadius
          color: Util.alpha(Color.accent, row.selected ? 0.14 : (rowMouse.containsMouse ? 0.07 : 0))
          Behavior on color { ColorAnimation { duration: 120 } }
          Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 2
            color: Color.accent
            opacity: row.selected ? 1 : 0
          }
        }

        MouseArea {
          id: rowMouse
          anchors.fill: parent
          hoverEnabled: true
          acceptedButtons: Qt.LeftButton | Qt.RightButton
          cursorShape: Qt.PointingHandCursor
          onEntered: card.host.settingsIndex = row.index
          onClicked: (mouse) => card.host.stepSetting(row.index, mouse.button === Qt.RightButton ? -1 : 1)
        }

        Text {
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          text: row.modelData.label
          color: Util.alpha(Color.foreground, row.selected ? 0.95 : 0.7)
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(12)
        }

        Row {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: card.host.px(8)
          Text {
            text: "‹"
            opacity: row.selected ? 0.8 : 0
            color: Color.accent
            font.family: Style.fontFamily
            font.pixelSize: card.host.px(13)
          }
          Text {
            text: card.host.settingLabel(row.modelData)
            color: row.selected ? Color.accent : Util.alpha(Color.foreground, 0.9)
            font.family: Style.fontFamily
            font.pixelSize: card.host.px(12)
            font.weight: Font.Medium
          }
          Text {
            text: "›"
            opacity: row.selected ? 0.8 : 0
            color: Color.accent
            font.family: Style.fontFamily
            font.pixelSize: card.host.px(13)
          }
        }
      }
    }

    Item { width: 1; height: card.host.px(8) }

    Text {
      width: parent.width
      text: card.host.tr("settingsFooter")
      color: Util.alpha(Color.foreground, 0.5)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(10)
      font.letterSpacing: 1
    }
    Text {
      width: parent.width
      text: card.host.canSave ? card.host.tr("saved") : card.host.tr("cantSave")
      color: card.host.canSave ? Util.alpha(Color.foreground, 0.35) : Color.urgent
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(10)
      wrapMode: Text.WordWrap
    }
  }
}
