import QtQuick
import qs.Commons

// "Now playing": any MPRIS player (Spotify, a browser tab, mpv...).
// Click / Enter takes you to the app. With several sources it shows "1/2";
// click there (or press [ ]) to switch.
CardFrame {
  id: card

  readonly property var player: host.player
  readonly property bool hasMedia: player !== null
  readonly property bool playing: hasMedia && player.isPlaying
  readonly property real length: hasMedia && player.lengthSupported ? player.length : 0
  readonly property real progress: length > 0 ? Math.min(1, Math.max(0, player.position / length)) : 0
  readonly property bool selected: host.selected === "media"
  readonly property string flashText: host.flash["media"] || ""

  width: host.mediaWidth
  height: host.mediaArtSize + host.px(28)
  border.color: selected ? Util.alpha(Color.accent, 0.85)
    : (cardMouse.containsMouse ? Util.alpha(Color.accent, 0.4) : Util.alpha(Color.foreground, 0.10))
  Behavior on border.color { ColorAnimation { duration: 140 } }

  opacity: host.mediaVisible ? (playing || selected ? 1 : 0.72) : 0

  function fmt(seconds) {
    if (!isFinite(seconds) || seconds < 0) seconds = 0
    var sec = Math.floor(seconds)
    var m = Math.floor(sec / 60)
    var h = Math.floor(m / 60)
    var ss = (sec % 60 < 10 ? "0" : "") + (sec % 60)
    if (h > 0) return h + ":" + ((m % 60) < 10 ? "0" : "") + (m % 60) + ":" + ss
    return m + ":" + ss
  }

  HoverHandler { onHoveredChanged: card.host.setHover("media", hovered) }

  // The whole card opens the app; the buttons (declared later) sit on top.
  MouseArea {
    id: cardMouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onEntered: card.host.hoverSelect("media")
    onClicked: card.host.activate("media", false)
  }

  // Selection tint
  Rectangle {
    anchors.fill: parent
    anchors.margins: 1
    radius: Style.cornerRadius
    color: Util.alpha(Color.accent, card.selected ? 0.08 : 0)
    Behavior on color { ColorAnimation { duration: 140 } }
  }

  // ---- Cover ----------------------------------------------------------------
  Item {
    id: artBox
    anchors.left: parent.left
    anchors.leftMargin: card.host.px(14)
    anchors.verticalCenter: parent.verticalCenter
    width: card.host.mediaArtSize
    height: card.host.mediaArtSize

    Rectangle {
      anchors.fill: parent
      radius: Style.cornerRadius
      color: Util.alpha(Color.foreground, 0.06)
      Text {
        anchors.centerIn: parent
        visible: art.status !== Image.Ready
        text: "󰝚"
        color: Color.accent
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(34)
      }
    }

    Image {
      id: art
      anchors.fill: parent
      source: card.hasMedia && card.player.trackArtUrl ? card.player.trackArtUrl : ""
      fillMode: Image.PreserveAspectCrop
      asynchronous: true
      smooth: true
      mipmap: true
      sourceSize.width: card.host.mediaArtSize * 2
      sourceSize.height: card.host.mediaArtSize * 2
      visible: status === Image.Ready
    }
  }

  // ---- Several sources: "Spotify · 1/2" --------------------------------------
  Rectangle {
    id: sourceTag
    visible: card.host.mprisList.length > 1
    anchors.top: parent.top
    anchors.right: parent.right
    anchors.topMargin: card.host.px(8)
    anchors.rightMargin: card.host.px(10)
    height: card.host.px(18)
    width: sourceText.implicitWidth + card.host.px(12)
    radius: Style.cornerRadius
    color: sourceMouse.containsMouse ? Util.alpha(Color.accent, 0.22) : Util.alpha(Color.foreground, 0.06)

    Text {
      id: sourceText
      anchors.centerIn: parent
      text: (card.hasMedia ? (card.player.identity || "") + " · " : "")
        + (card.host.playerIndex + 1) + "/" + card.host.mprisList.length
      color: Util.alpha(Color.foreground, 0.7)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(10)
    }
    MouseArea {
      id: sourceMouse
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: card.host.cyclePlayer(1)
    }
  }

  // ---- Text + progress ------------------------------------------------------
  Column {
    id: info
    anchors.left: artBox.right
    anchors.leftMargin: card.host.px(16)
    anchors.right: parent.right
    anchors.rightMargin: card.host.px(16)
    anchors.verticalCenter: parent.verticalCenter
    spacing: card.host.px(3)

    Text {
      width: parent.width - (sourceTag.visible ? sourceTag.width + 4 : 0)
      text: card.hasMedia ? (card.player.trackTitle || card.host.tr("untitledTrack")) : ""
      color: Color.foreground
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(15)
      font.weight: Font.DemiBold
      elide: Text.ElideRight
    }

    Text {
      width: parent.width
      text: card.flashText || (card.hasMedia ? (card.player.trackArtist || card.player.identity || "") : "")
      color: card.flashText ? Color.urgent : Util.alpha(Color.foreground, 0.65)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(12)
      elide: Text.ElideRight
    }

    Item { width: 1; height: card.host.px(6) }

    Rectangle {
      width: parent.width
      height: Math.max(2, card.host.px(3))
      radius: height / 2
      color: Util.alpha(Color.foreground, 0.14)
      visible: card.length > 0

      Rectangle {
        width: parent.width * card.progress
        height: parent.height
        radius: parent.radius
        color: Color.accent
        Behavior on width { NumberAnimation { duration: 900; easing.type: Easing.Linear } }
      }
    }

    Item {
      width: parent.width
      height: card.host.px(26)

      Text {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        visible: card.length > 0
        text: card.hasMedia ? card.fmt(card.player.position) + " / " + card.fmt(card.length) : ""
        color: Util.alpha(Color.foreground, 0.55)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(11)
      }

      Row {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: card.host.px(6)

        Repeater {
          model: [
            { icon: "󰒮", action: "prev", enabled: card.hasMedia && card.player.canGoPrevious },
            { icon: card.playing ? "󰏤" : "󰐊", action: "toggle", enabled: card.hasMedia && card.player.canTogglePlaying },
            { icon: "󰒭", action: "next", enabled: card.hasMedia && card.player.canGoNext }
          ]

          delegate: Rectangle {
            required property var modelData
            width: card.host.px(26)
            height: width
            radius: Style.cornerRadius
            color: btn.containsMouse && modelData.enabled ? Util.alpha(Color.accent, 0.22) : "transparent"
            opacity: modelData.enabled ? 1 : 0.35

            Text {
              anchors.centerIn: parent
              text: modelData.icon
              color: modelData.action === "toggle" ? Color.accent : Color.foreground
              font.family: Style.fontFamily
              font.pixelSize: card.host.px(modelData.action === "toggle" ? 18 : 15)
            }

            MouseArea {
              id: btn
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              enabled: modelData.enabled
              onClicked: {
                var p = card.player
                if (!p) return
                if (modelData.action === "prev") p.previous()
                else if (modelData.action === "next") p.next()
                else p.togglePlaying()
              }
            }
          }
        }
      }
    }
  }
}
