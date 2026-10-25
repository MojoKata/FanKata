import QtQuick
import "."

Item {
    id: root
    property var probe: null
    readonly property bool hasValue: !!probe && probe.value !== null && probe.value !== undefined
    Text {
        x: 12; y: 9
        text: root.probe ? root.probe.name : ""
        color: Theme.text; font.pixelSize: 13; font.bold: true; font.family: Theme.mono
        width: parent.width - 100; elide: Text.ElideRight
    }
    Text {
        x: 12; y: 29
        text: root.probe ? (root.probe.error && root.probe.kind === "custom" ? root.probe.error : root.probe.desc) : ""
        color: root.probe && root.probe.error && root.probe.kind === "custom" ? Theme.warn : Theme.muted
        font.pixelSize: root.probe && root.probe.kind === "custom" ? 11 : 12
        font.family: root.probe && root.probe.kind === "custom" && !root.probe.error ? Theme.mono : Qt.application.font.family
        width: parent.width - 100; elide: Text.ElideRight
    }
    Text {
        anchors.right: parent.right; anchors.rightMargin: 12; y: 8
        text: root.hasValue ? Theme.fmt1(root.probe.value) + "°" : "—"
        color: root.hasValue ? Theme.heat(root.probe.value) : Theme.faint
        font.pixelSize: 16; font.bold: true
    }
    Sparkline {
        anchors.right: parent.right; anchors.rightMargin: 12; y: 31
        width: 62; height: 14
        values: root.probe ? root.probe.history : []
        window: 60
        color: root.hasValue ? Theme.heat(root.probe.value) : Theme.faint
    }
}
