import QtQuick
import "."

Rectangle {
    id: root
    property string icon
    property bool round: false
    property bool active: false
    property bool outlined: !round
    property real iconSize: round ? 12 : 16
    property real lineWidth: round ? 1.8 : 1.6
    property string tip: ""
    signal clicked()
    implicitWidth: round ? 28 : 34
    implicitHeight: implicitWidth
    width: implicitWidth
    height: implicitHeight
    radius: round ? width / 2 : 10
    color: active ? Theme.accentSoft : round ? (area.containsMouse ? Theme.border : Theme.track)
                                              : (area.containsMouse ? Theme.hover : Theme.surface)
    border.width: active ? 1.5 : (outlined ? 1 : 0)
    border.color: active ? Theme.accent : Theme.border
    Icon {
        anchors.centerIn: parent
        name: root.icon
        size: root.iconSize
        lineWidth: root.lineWidth
        color: root.active ? Theme.accent : Theme.muted
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
