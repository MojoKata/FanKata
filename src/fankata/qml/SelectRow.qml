import QtQuick
import "."

// One entry in a Select: optional curve thumbnail or probe icon, title, subtitle, trailing value.
Item {
    id: root
    property var entry: null
    property bool compact: false
    implicitHeight: 46
    readonly property bool isCurve: !!entry && !!entry.points
    Rectangle {
        id: thumb
        visible: root.isCurve
        x: 10; anchors.verticalCenter: parent.verticalCenter
        width: 52; height: 30; radius: 7
        color: Theme.surface
        CurveChart {
            anchors.fill: parent; anchors.margins: 3
            visible: root.isCurve
            points: root.isCurve ? root.entry.points : []
            labels: false; markers: false; lineWidth: 2; background: Theme.surface
        }
    }
    Icon {
        id: thermo
        visible: !!root.entry && !root.isCurve && root.entry.kind !== "none"
        x: 14; anchors.verticalCenter: parent.verticalCenter
        name: "thermo"
        color: root.entry && root.entry.value !== null && root.entry.value !== undefined ? Theme.heat(root.entry.value) : Theme.faint
    }
    Row {
        x: root.isCurve ? 74 : thermo.visible ? 38 : 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        Text {
            text: root.entry ? root.entry.title : ""
            color: root.entry && root.entry.kind === "none" ? Theme.muted : Theme.text
            font.pixelSize: root.isCurve ? 14 : 13
            font.bold: root.isCurve
            font.family: root.entry && root.entry.mono ? Theme.mono : Qt.application.font.family
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.entry && root.entry.subtitle ? root.entry.subtitle : ""
            color: Theme.muted; font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight
        }
    }
    Text {
        visible: !!root.entry && root.entry.value !== undefined && root.entry.value !== null
        anchors.right: parent.right; anchors.rightMargin: 44
        anchors.verticalCenter: parent.verticalCenter
        text: root.entry && root.entry.value !== null && root.entry.value !== undefined ? Theme.fmt1(root.entry.value) + " °C" : ""
        color: Theme.text; font.pixelSize: 13; font.bold: true
    }
}
