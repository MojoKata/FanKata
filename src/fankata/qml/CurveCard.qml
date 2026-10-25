import QtQuick
import "."

Rectangle {
    id: root
    property var curve: null
    property bool selected: false
    signal clicked()
    width: 260; height: 100; radius: 14
    color: selected ? Theme.alpha(Theme.accent, Theme.dark ? 0.12 : 0.07) : Theme.surface
    border.width: selected ? 2 : 1
    border.color: selected ? Theme.accent : area.containsMouse ? Theme.borderStrong : Theme.border
    Rectangle {
        x: 10; y: 10; width: parent.width - 20; height: 52; radius: 8; color: Theme.input
        CurveChart {
            anchors.fill: parent; anchors.margins: 2
            points: root.curve ? root.curve.points : []
            labels: false; markerRadius: 2.4; lineWidth: 2.2; background: Theme.input
        }
    }
    Text { x: 12; y: 72; text: root.curve ? root.curve.name : ""; color: Theme.text; font.pixelSize: 14; font.bold: true; width: 140; elide: Text.ElideRight }
    Text {
        anchors.right: parent.right; anchors.rightMargin: 12; y: 74
        readonly property int used: root.curve ? root.curve.users.length : 0
        text: root.curve ? root.curve.points.length + " pts · " + (used ? used + (used > 1 ? " fans" : " fan") : "unused") : ""
        color: used ? Theme.muted : Theme.faint; font.pixelSize: 12
    }
    MouseArea { id: area; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.clicked() }
}
