import QtQuick
import QtQuick.Controls.Basic
import "."

Rectangle {
    id: root
    property string view: "fans"
    property var window: null
    signal viewSelected(string view)
    signal about()
    signal troubleshoot()
    property alias menu: appMenu          // for the screenshot tour
    height: 52
    color: Theme.surface
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }

    // drag to move, double-click to maximize (the window has no system title bar)
    DragHandler {
        target: null
        onActiveChanged: if (active && root.window) root.window.startSystemMove()
    }
    TapHandler {
        onDoubleTapped: if (root.window) root.window.visibility === Window.Maximized ? root.window.showNormal() : root.window.showMaximized()
    }

    Image { x: 18; y: 12; width: 28; height: 28; source: "assets/art/fankata.svg"; sourceSize: Qt.size(56, 56); smooth: true }
    Text { x: 56; anchors.verticalCenter: parent.verticalCenter; text: "Fankata"; color: Theme.text; font.pixelSize: 15; font.bold: true }

    Rectangle {
        id: seg
        anchors.centerIn: parent
        width: 248; height: 34; radius: 10; color: Theme.track
        Row {
            x: 3; y: 3
            Repeater {
                model: [["fans", "fan", "Fans"], ["curves", "curve", "Curves"]]
                Rectangle {
                    readonly property bool on: root.view === modelData[0]
                    width: (seg.width - 6) / 2; height: 28; radius: 8
                    color: on ? Theme.segOn : "transparent"
                    Row {
                        anchors.centerIn: parent; spacing: 6
                        Icon { name: modelData[1]; color: parent.parent.on ? Theme.text : Theme.muted; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: modelData[2]; color: parent.parent.on ? Theme.text : Theme.muted; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.viewSelected(modelData[0]) }
                }
            }
        }
    }

    Item {
        id: dotsBtn
        anchors.right: closeBtn.left; anchors.rightMargin: 20; anchors.verticalCenter: parent.verticalCenter
        width: 28; height: 28
        Rectangle { anchors.fill: parent; radius: 14; color: dotsArea.containsMouse || appMenu.visible ? Theme.track : "transparent" }
        Icon { anchors.centerIn: parent; name: "dots"; color: Theme.muted }
        MouseArea { id: dotsArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: appMenu.open() }
        PopMenu {
            id: appMenu
            menuWidth: 300
            x: dotsBtn.width - menuWidth; y: 38
            readonly property string mode: themeOverride || backend.prefs.theme || "system"
            readonly property bool on: backend.connected
            items: [
                // requirement 4.6: turning the service off returns every fan to firmware control
                { key: "service", type: "check", text: "Fan control service", checked: on, enabled: !backend.serviceBusy,
                  subtext: backend.serviceBusy ? (on ? "Turning off…" : "Turning on…")
                           : on ? "On · fans follow their curves" : "Off · fans under firmware control" },
                { key: "troubleshoot", icon: "lifebuoy", text: "Troubleshoot fans…" },     // requirement 4.7
                { type: "separator" },
                { key: "system", type: "radio", text: "Match system", checked: mode === "system" },
                { key: "dark", type: "radio", text: "Dark", checked: mode === "dark" },
                { key: "light", type: "radio", text: "Light", checked: mode === "light" },
                { type: "separator" },
                { key: "about", text: "About Fankata" },
                { key: "quit", text: "Quit" }]
            onTriggered: key => {
                if (key === "service") backend.setServiceEnabled(!backend.connected)
                else if (key === "about") root.about()
                else if (key === "troubleshoot") root.troubleshoot()
                else if (key === "quit") Qt.quit()
                else backend.setPref("theme", key)
            }
        }
    }
    IconButton {
        id: closeBtn
        anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter
        round: true; icon: "x"
        onClicked: Qt.quit()
    }
}
