import QtQuick
import "."

// Text button with optional icon: secondary (outlined) by default, or primary / danger.
Rectangle {
    id: root
    property string text
    property string icon: ""
    property bool primary: false
    property bool danger: false
    property bool enabledButton: true
    signal clicked()
    implicitHeight: 34
    height: implicitHeight
    width: row.implicitWidth + 28
    radius: 10
    readonly property color fg: !enabledButton ? Theme.faint : primary ? "#ffffff" : danger ? Theme.err : Theme.text
    color: primary ? (enabledButton ? (area.containsMouse ? Qt.lighter(Theme.accent, 1.08) : Theme.accent) : Theme.track)
                   : (area.containsMouse && enabledButton ? Theme.hover : Theme.surface)
    border.width: primary ? 0 : 1
    border.color: Theme.border
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Icon { visible: root.icon !== ""; name: root.icon; color: root.fg; anchors.verticalCenter: parent.verticalCenter }
        Text {
            text: root.text; color: root.fg; font.pixelSize: 13; font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabledButton ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.enabledButton) root.clicked()
    }
}
