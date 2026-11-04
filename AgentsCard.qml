import QtQuick
import qs.Commons

// "Agents": every AI coding agent on the machine and what it is doing.
// Each row takes you to the agent's window (or session).
CardFrame {
  id: card

  readonly property var groups: host.groups
  readonly property bool empty: groups.length === 0

  width: host.panelWidth
  height: content.implicitHeight + host.px(36)
  alert: host.waitingCount > 0
  opacity: host.shown("agents") && (!empty || host.cfg.agents.showWhenEmpty) ? 1 : 0

  HoverHandler { onHoveredChanged: card.host.setHover("agents", hovered) }

  component AgentRow: Item {
    id: row
    required property var agent
    readonly property string navKey: "agent:" + agent.key
    readonly property bool working: agent.state === "working"
    readonly property bool waiting: agent.state === "waiting"
    readonly property string flashText: card.host.flash[navKey] || ""
    readonly property string detail: agent.detailCode ? card.host.tr(agent.detailCode) : (agent.detail || "")

    width: parent ? parent.width : 0
    height: card.host.px(20)

    NavRow { host: card.host; navKey: row.navKey }

    // State: a pulsing ring while working, the urgent colour when it waits for you.
    Item {
      id: dotBox
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      width: card.host.px(10)
      height: width

      Rectangle {
        anchors.centerIn: parent
        width: card.host.px(14); height: width; radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: Color.accent
        visible: row.working
        opacity: 0
        SequentialAnimation on opacity {
          running: row.working
          loops: Animation.Infinite
          NumberAnimation { from: 0.7; to: 0; duration: 1400; easing.type: Easing.OutCubic }
        }
        SequentialAnimation on scale {
          running: row.working
          loops: Animation.Infinite
          NumberAnimation { from: 0.6; to: 1.3; duration: 1400; easing.type: Easing.OutCubic }
        }
      }

      Rectangle {
        anchors.centerIn: parent
        width: card.host.px(8); height: width; radius: width / 2
        color: row.working ? Color.accent : (row.waiting ? Color.urgent : "transparent")
        border.width: row.working || row.waiting ? 0 : 1
        border.color: Util.alpha(Color.foreground, 0.45)
        Behavior on color { ColorAnimation { duration: 300 } }
      }
    }

    Text {
      id: nameText
      anchors.left: dotBox.right
      anchors.leftMargin: card.host.px(10)
      anchors.verticalCenter: parent.verticalCenter
      width: Math.min(implicitWidth, parent.width - dotBox.width - stateLabel.implicitWidth - card.host.px(24))
      text: row.agent.name || card.host.tr("untitled")
      color: Util.alpha(Color.foreground, row.working || row.waiting ? 0.95 : 0.7)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(12)
      font.weight: row.working ? Font.Medium : Font.Normal
      elide: Text.ElideRight
    }

    Text {
      anchors.left: nameText.right
      anchors.leftMargin: card.host.px(7)
      anchors.right: stateLabel.left
      anchors.rightMargin: card.host.px(10)
      anchors.baseline: nameText.baseline
      text: row.detail
      visible: text !== ""
      color: Util.alpha(Color.foreground, 0.38)
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(10)
      elide: Text.ElideRight
    }

    Text {
      id: stateLabel
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      text: row.flashText || card.host.stateText(row.agent)
      color: row.flashText ? Color.urgent
        : (row.working ? Color.accent : (row.waiting ? Color.urgent : Util.alpha(Color.foreground, 0.45)))
      font.family: Style.fontFamily
      font.pixelSize: card.host.px(11)
    }
  }

  Column {
    id: content
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.margins: card.host.px(18)
    spacing: card.host.px(14)

    // Header
    Item {
      width: parent.width
      height: title.implicitHeight

      Row {
        spacing: card.host.px(8)
        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: card.host.px(6); height: width; radius: width / 2
          color: card.host.waitingCount > 0 ? Color.urgent : Color.accent
        }
        Text {
          id: title
          text: card.host.tr("agents")
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
        text: card.host.waitingCount > 0
          ? card.host.tr(card.host.waitingCount === 1 ? "nWaiting1" : "nWaitingN", card.host.waitingCount)
          : (card.host.workingCount > 0 ? card.host.tr("nWorking", card.host.workingCount) : card.host.tr("calm"))
        color: card.host.waitingCount > 0 ? Color.urgent : Util.alpha(Color.foreground, 0.55)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(11)
      }
    }

    // Nothing running yet.
    Column {
      visible: card.empty
      width: parent.width
      spacing: card.host.px(4)
      Text {
        text: card.host.tr("noAgents")
        color: Util.alpha(Color.foreground, 0.7)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(12)
      }
      Text {
        width: parent.width
        text: card.host.tr("noAgentsHint")
        color: Util.alpha(Color.foreground, 0.4)
        font.family: Style.fontFamily
        font.pixelSize: card.host.px(10)
        elide: Text.ElideRight
      }
    }

    Repeater {
      model: card.groups

      delegate: Column {
        id: group
        required property var modelData
        readonly property var usage: modelData.usage || null
        width: content.width
        spacing: card.host.px(7)

        Item {
          width: parent.width
          height: groupLabel.implicitHeight

          Text {
            id: groupLabel
            anchors.left: parent.left
            anchors.right: usageText.left
            anchors.rightMargin: card.host.px(8)
            text: group.modelData.label
            color: Util.alpha(Color.foreground, 0.5)
            font.family: Style.fontFamily
            font.pixelSize: card.host.px(10)
            font.letterSpacing: 2
            elide: Text.ElideRight
          }
          // Plan usage from Omarchy's Agents widget, e.g. "42% · 5h".
          Text {
            id: usageText
            anchors.right: parent.right
            anchors.baseline: groupLabel.baseline
            visible: !!group.usage
            text: group.usage ? Math.round(group.usage.percent * 100) + "%" + (group.usage.short ? " · " + group.usage.short : "") : ""
            color: group.usage && group.usage.percent >= 0.9 ? Color.urgent : Util.alpha(Color.foreground, 0.4)
            font.family: Style.fontFamily
            font.pixelSize: card.host.px(10)
          }
        }

        Repeater {
          model: group.modelData.agents.slice(0, card.host.cfg.agents.maxPerGroup)
          delegate: AgentRow {
            required property var modelData
            agent: modelData
          }
        }

        Text {
          visible: group.modelData.agents.length > card.host.cfg.agents.maxPerGroup
          text: card.host.tr("more", group.modelData.agents.length - card.host.cfg.agents.maxPerGroup)
          color: Util.alpha(Color.foreground, 0.45)
          font.family: Style.fontFamily
          font.pixelSize: card.host.px(11)
          leftPadding: card.host.px(20)
        }
      }
    }
  }
}
