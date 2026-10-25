import QtQuick
import QtQuick.Controls.Basic
import "."

// Select field with a styled drop-down list. model: [{key, title, subtitle, points?, value?, mono?, kind?}]
Rectangle {
    id: root
    property var model: []
    property string current: ""
    property bool clearable: false
    property string placeholder: "Choose…"
    property bool enabledSelect: true
    signal picked(string key)
    signal cleared()
    height: 46
    radius: 12
    color: Theme.input
    border.width: pop.visible ? 2 : 1
    border.color: pop.visible ? Theme.accent : Theme.border
    opacity: enabledSelect ? 1 : 0.45
    readonly property var cur: {
        for (const m of model) if (m.key === current) return m
        return null
    }
    SelectRow {
        anchors.fill: parent
        anchors.rightMargin: root.clearable && root.cur ? 40 : 0
        entry: root.cur || { key: "", title: root.placeholder, kind: "none" }
    }
    Rectangle {
        visible: root.clearable && !!root.cur
        anchors.right: parent.right; anchors.rightMargin: 47
        anchors.verticalCenter: parent.verticalCenter
        width: 22; height: 22; radius: 11
        color: clearArea.containsMouse ? Theme.border : Theme.track
        Icon { anchors.centerIn: parent; name: "x"; size: 10; lineWidth: 1.8; color: Theme.muted }
        MouseArea {
            id: clearArea; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor; enabled: root.enabledSelect
            onClicked: root.cleared()
        }
    }
    Rectangle {
        visible: root.clearable && !!root.cur
        x: parent.width - 38; y: 12; width: 1; height: 22; color: Theme.border
    }
    Icon { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; name: "chevDown"; color: Theme.muted }
    MouseArea {
        anchors.fill: parent
        anchors.rightMargin: root.clearable && root.cur ? 40 : 0
        z: -1
        enabled: root.enabledSelect
        cursorShape: Qt.PointingHandCursor
        onClicked: pop.open()
    }
    Popup {
        id: pop
        y: root.height + 6
        width: root.width
        padding: 6
        height: Math.min(list.contentHeight + 12, 320)
        background: Rectangle { radius: 12; color: Theme.raised; border.color: Theme.border }
        contentItem: ListView {
            id: list
            clip: true
            layer.enabled: GraphicsInfo.api === GraphicsInfo.Software   // clips Shape icons
            Rectangle { z: -1; width: parent.width; height: Math.max(list.height, list.contentHeight); color: Theme.raised }
            model: root.model
            boundsBehavior: Flickable.StopAtBounds
            delegate: Rectangle {
                width: ListView.view.width
                height: 46
                radius: 9
                color: modelData.key === root.current ? Theme.accentSoft : rowArea.containsMouse ? Theme.hover : "transparent"
                SelectRow { anchors.fill: parent; entry: modelData }
                MouseArea {
                    id: rowArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: { pop.close(); root.picked(modelData.key) }
                }
            }
        }
    }
}
