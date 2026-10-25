import QtQuick
import "."

Rectangle {
    id: root
    property string kind: "info"
    function show(k, text) { kind = k; label.text = text; opacity = 1; hide.restart() }
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom; anchors.bottomMargin: 28
    width: Math.min(parent.width - 80, row.implicitWidth + 36); height: 44; radius: 12
    color: kind === "error" ? Theme.err : Theme.tipBg
    opacity: 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: 180 } }
    Row {
        id: row
        anchors.centerIn: parent; spacing: 10
        Icon { name: root.kind === "error" ? "warn" : "info"; color: root.kind === "error" ? "#ffffff" : Theme.tipFg; anchors.verticalCenter: parent.verticalCenter }
        Text { id: label; color: root.kind === "error" ? "#ffffff" : Theme.tipFg; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
    }
    Timer { id: hide; interval: 4500; onTriggered: root.opacity = 0 }
    MouseArea { anchors.fill: parent; onClicked: root.opacity = 0 }
}
