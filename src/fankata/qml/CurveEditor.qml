import QtQuick
import QtQuick.Controls.Basic
import "."

Item {
    id: root
    property var curve: null
    signal message(string text)
    signal renamed(string name)
    signal deleted()
    property alias chart: chart
    property alias table: table
    property alias menu: curveMenu
    readonly property var users: curve ? curve.users : []
    readonly property var fansUsing: curve ? backend.fans.filter(f => f.curve === curve.name) : []

    Row {
        x: 0; y: 22; spacing: 10
        visible: !nameEdit.visible
        Text { id: title; text: root.curve ? root.curve.name : ""; color: Theme.text; font.pixelSize: 28; font.bold: true }
        Icon {
            anchors.verticalCenter: title.verticalCenter; name: "pencil"; color: Theme.muted
            MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                        onClicked: { nameEdit.text = root.curve.name; nameEdit.visible = true; nameEdit.forceActiveFocus(); nameEdit.selectAll() } }
        }
    }
    TextField {
        id: nameEdit
        visible: false
        y: 20; width: 320; height: 40
        font.pixelSize: 22; font.bold: true; color: Theme.text
        background: Rectangle { radius: 8; color: Theme.input; border.color: Theme.accent; border.width: 2 }
        onAccepted: {
            const e = backend.renameCurve(root.curve.name, text)
            if (e) root.message(e); else root.renamed(text.trim())
            visible = false
        }
        onActiveFocusChanged: if (!activeFocus && visible) accepted()
        Keys.onEscapePressed: visible = false
    }
    Row {
        y: 60; spacing: 6
        Text { text: root.users.length ? "Used by" : "Not used by any fan"; color: Theme.muted; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
        Repeater {
            model: root.fansUsing
            Pill { text: modelData.name; fg: Theme.text; showDot: true; height: 22; border.color: Theme.border; border.width: 1
                   dot: modelData.probe_value !== null && modelData.probe_value !== undefined ? Theme.heat(modelData.probe_value) : Theme.faint }
        }
    }
    IconButton {
        id: moreButton
        anchors.right: parent.right; y: 24
        icon: "more"; active: curveMenu.visible
        onClicked: curveMenu.visible ? curveMenu.close() : curveMenu.open()
        PopMenu {
            id: curveMenu
            menuWidth: 280
            x: moreButton.width - menuWidth; y: 42
            items: root.curve ? [
                { key: "duplicate", text: "Duplicate curve", icon: "copy", enabled: backend.connected },
                { type: "separator" },
                { key: "zero", type: "check", text: "Allow zero", subtext: "Speeds below 20 % are allowed", checked: root.curve.allowZero, enabled: backend.connected },
                { type: "separator" },
                { key: "delete", text: "Delete curve", icon: "trash", danger: true, enabled: root.users.length === 0 && backend.connected,
                  note: root.users.length ? "Used by " + root.users.length + (root.users.length > 1 ? " fans" : " fan") : "" }] : []
            onTriggered: key => {
                let e = ""
                if (key === "duplicate") { const n = backend.duplicateCurve(root.curve.name); if (n) root.renamed(n) }
                else if (key === "zero") e = backend.setAllowZero(root.curve.name, !root.curve.allowZero)
                else if (key === "delete") { e = backend.deleteCurve(root.curve.name); if (!e) root.deleted() }
                if (e) root.message(e)
            }
        }
    }
    Rectangle {
        id: chartCard
        y: 94; width: parent.width; height: Math.max(220, Math.min(330, root.height - 94 - 200))
        radius: 16; color: Theme.surface; border.color: Theme.border
        Rectangle { z: -1; anchors.fill: parent; anchors.topMargin: 3; anchors.bottomMargin: -3; radius: 16; color: "#000000"; opacity: Theme.dark ? 0.28 : 0.05 }
        CurveChart {
            id: chart
            anchors.fill: parent; anchors.margins: 10
            interactive: backend.connected
            curveName: root.curve ? root.curve.name : ""
            points: root.curve ? root.curve.points : []
            allowZero: root.curve ? root.curve.allowZero : false
            markerRadius: 6; lineWidth: 3.4
            ops: root.fansUsing.map(f => ({ v: f.probe_value, label: f.name + " · " + Theme.fmt1(f.probe_value) + "°" }))
            onMessage: text => root.message(text)
        }
    }
    PointsTable {
        id: table
        y: chartCard.y + chartCard.height + 26
        width: parent.width
        curve: root.curve
        highlight: chart.hoverKind === "remove" ? chart.hoverIndex : -1
        onMessage: text => root.message(text)
    }
}
