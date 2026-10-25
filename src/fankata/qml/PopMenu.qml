import QtQuick
import QtQuick.Controls.Basic
import "."

// Popup menu. items: [{key, text, subtext, icon, type: "action"|"check"|"radio"|"separator",
//                      checked, enabled, danger, note}]
Popup {
    id: root
    property var items: []
    property real menuWidth: 300
    signal triggered(string key)
    width: menuWidth
    padding: 6
    modal: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
    background: Rectangle {
        radius: 14
        color: Theme.raised
        border.color: Theme.border
        Rectangle {    // soft shadow
            z: -1; anchors.fill: parent; anchors.margins: -1; anchors.topMargin: 4
            radius: 15; color: "#000000"; opacity: Theme.dark ? 0.35 : 0.08
        }
    }
    contentItem: Column {
        spacing: 2
        Repeater {
            model: root.items
            delegate: Loader {
                width: root.menuWidth - 12
                sourceComponent: modelData.type === "separator" ? sep : row
                property var entry: modelData
            }
        }
    }
    Component {
        id: sep
        Item { height: 9; Rectangle { anchors.verticalCenter: parent.verticalCenter; x: 6; width: parent.width - 12; height: 1; color: Theme.border } }
    }
    Component {
        id: row
        Rectangle {
            id: r
            readonly property bool on: entry.enabled !== false
            readonly property color fg: !on ? Theme.faint : entry.danger ? Theme.err : Theme.text
            height: entry.subtext || entry.note ? 58 : 38
            radius: 10
            color: area.containsMouse && on ? Theme.hover : "transparent"
            Rectangle {
                id: box
                visible: entry.type === "check" || entry.type === "radio"
                x: 12; anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20; radius: entry.type === "radio" ? 10 : 6
                color: !!entry.checked ? Theme.accent : "transparent"
                border.width: !!entry.checked ? 0 : 1.6
                border.color: Theme.borderStrong
                Icon { anchors.centerIn: parent; visible: !!entry.checked && entry.type === "check"; name: "check"; size: 14; lineWidth: 2.2; color: "#ffffff" }
                Rectangle { anchors.centerIn: parent; visible: !!entry.checked && entry.type === "radio"; width: 8; height: 8; radius: 4; color: "#ffffff" }
            }
            Rectangle {
                id: badge
                visible: !box.visible && !!entry.icon
                x: 10; anchors.verticalCenter: parent.verticalCenter
                width: 30; height: 30; radius: 15
                color: entry.danger || !r.on ? "transparent" : Theme.accentSoft
                Icon { anchors.centerIn: parent; name: entry.icon || ""; color: entry.danger || !r.on ? r.fg : Theme.accent; lineWidth: 1.8 }
            }
            Column {
                x: box.visible || badge.visible ? 50 : 14
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Text { text: entry.text; color: r.fg; font.pixelSize: 14; font.bold: true }
                Text {
                    visible: !!(entry.subtext || entry.note)
                    text: entry.subtext || entry.note || ""
                    color: r.on ? Theme.muted : Theme.faint; font.pixelSize: 12
                }
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: r.on ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: if (r.on) { root.close(); root.triggered(entry.key) }
            }
        }
    }
}
