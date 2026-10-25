import QtQuick
import "."

Rectangle {
    id: root
    property bool open: true
    signal toggle()
    signal editProbe(string name)
    signal newProbe()
    color: Theme.surface
    Rectangle { width: 1; height: parent.height; color: Theme.border }
    readonly property var aliases: ["sys.cpu", "sys.gpu", "sys.nvme", "sys.coolant"]
    readonly property var system: backend.probes.filter(p => p.kind === "system")
    readonly property var primary: system.filter(p => aliases.indexOf(p.name) >= 0)
    readonly property var others: system.filter(p => aliases.indexOf(p.name) < 0)
    property bool showAll: false
    readonly property var custom: backend.probes.filter(p => p.kind === "custom")

    // collapsed rail
    Column {
        visible: !root.open
        anchors.horizontalCenter: parent.horizontalCenter
        y: 18; spacing: 22
        IconButton { icon: "panel"; onClicked: root.toggle(); anchors.horizontalCenter: parent.horizontalCenter }
        Icon { name: "thermo"; size: 18; color: Theme.accent; anchors.horizontalCenter: parent.horizontalCenter }
        Item {
            width: 20; height: 70; anchors.horizontalCenter: parent.horizontalCenter
            Text { anchors.centerIn: parent; rotation: -90; text: "Probes"; color: Theme.muted; font.pixelSize: 14; font.bold: true }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.toggle() }
        }
    }

    Item {
        visible: root.open
        anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18
        Row {
            y: 25; spacing: 8
            Icon { name: "thermo"; size: 18; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "Probes"; color: Theme.text; font.pixelSize: 17; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
        }
        IconButton { anchors.right: panelBtn.left; anchors.rightMargin: 8; y: 19; icon: "plus"; onClicked: root.newProbe() }
        IconButton { id: panelBtn; anchors.right: parent.right; y: 19; icon: "panel"; onClicked: root.toggle() }
        Flickable {
            id: probeFlick
            anchors.fill: parent; anchors.topMargin: 66
            contentHeight: list.height + 24
            clip: true
            layer.enabled: GraphicsInfo.api === GraphicsInfo.Software   // clips Shape icons
            Rectangle { z: -1; width: parent.width; height: Math.max(probeFlick.height, list.height + 24); color: Theme.surface }   // layers need an opaque backing
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: list
                width: parent.width
                Item {
                    width: parent.width; height: 26
                    Text { text: "SYSTEM"; color: Theme.faint; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2 }
                    Text { anchors.right: parent.right; text: "read-only"; color: Theme.faint; font.pixelSize: 11 }
                }
                Repeater {
                    model: root.primary.length ? (root.showAll ? root.primary.concat(root.others) : root.primary) : root.system
                    Item {
                        width: list.width; height: 54
                        Rectangle { visible: index > 0; x: 12; width: parent.width - 24; height: 1; color: Theme.border }
                        ProbeRow { anchors.fill: parent; probe: modelData }
                    }
                }
                Item {
                    visible: root.primary.length > 0 && root.others.length > 0
                    width: list.width; height: 34
                    Row {
                        x: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                        Icon { name: root.showAll ? "chevDown" : "chevRight"; size: 14; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: root.showAll ? "Fewer sensors" : "More sensors (" + root.others.length + ")"; color: Theme.accent; font.pixelSize: 13; font.bold: true }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.showAll = !root.showAll }
                }
                Item { width: 1; height: 16 }
                Text { text: "CUSTOM"; color: Theme.faint; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2; height: 24 }
                Repeater {
                    model: root.custom
                    Item {
                        width: list.width; height: 62
                        Rectangle {
                            width: parent.width; height: 54; radius: 12
                            color: rowArea.containsMouse ? Theme.hover : Theme.input; border.color: Theme.border
                            ProbeRow { anchors.fill: parent; probe: modelData }
                            MouseArea { id: rowArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.editProbe(modelData.name) }
                        }
                    }
                }
                Item { width: 1; height: 4 }
                Rectangle {
                    width: list.width; height: 40; radius: 12
                    color: newArea.containsMouse ? Theme.hover : "transparent"
                    border.color: Theme.borderStrong; border.width: 1.2
                    Row {
                        anchors.centerIn: parent; spacing: 6
                        Icon { name: "plus"; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "New custom probe"; color: Theme.accent; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                    }
                    MouseArea { id: newArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.newProbe() }
                }
            }
        }
    }
}
