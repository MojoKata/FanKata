import QtQuick
import "."

Rectangle {
    id: root
    property string text
    property color fg: Theme.muted
    property color dot: "transparent"
    property bool showDot: false
    property bool mono: false
    property bool bold: true
    property int size: 12
    property string icon: ""
    property real u: 1                  // scale factor (Fan tiles, requirement 5.2.5)
    implicitHeight: 24 * u
    height: implicitHeight
    radius: height / 2
    width: row.implicitWidth + (showDot ? 22 : 20) * u
    color: Theme.input
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7 * root.u
        Rectangle {
            visible: root.showDot
            width: 7 * root.u; height: 7 * root.u; radius: 3.5 * root.u
            color: root.dot
            anchors.verticalCenter: parent.verticalCenter
        }
        Icon {
            visible: root.icon !== ""
            name: root.icon; size: 14 * root.u; color: root.fg
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.text
            color: root.fg
            font.pixelSize: Math.round(root.size * root.u)
            font.bold: root.bold
            font.family: root.mono ? Theme.mono : Qt.application.font.family
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
