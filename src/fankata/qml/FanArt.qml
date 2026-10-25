import QtQuick
import "."

// Layered device illustration. The rotor spins at a rate that follows the real RPM,
// so a Speed pulse is visible on screen in step with the physical fan (requirement 5.5.3).
Item {
    id: root
    property var fan: null
    readonly property string kind: fan ? fan.type : "case"
    readonly property bool active: !!fan && (fan.managed || fan.pulsing)
    readonly property bool pulsing: !!fan && fan.pulsing
    property real rpm: fan && fan.rpm ? fan.rpm : 0
    Behavior on rpm { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
    property real angle: (fan && fan.index ? fan.index * 23 : 0)
    width: 240; height: 150

    // centres of rotation in the 240×150 art (assets/art/centres.json)
    readonly property point centre: kind === "aio" ? Qt.point(112, 75) : Qt.point(120, 75)

    Repeater {
        model: 3
        Rectangle {
            id: ripple
            visible: root.pulsing
            width: 124; height: 124; radius: 62
            x: root.centre.x - 62; y: root.centre.y - 62
            color: "transparent"
            border.color: Theme.accent
            border.width: 2
            opacity: 0
            SequentialAnimation on scale {
                running: root.pulsing
                loops: Animation.Infinite
                PauseAnimation { duration: index * 500 }
                NumberAnimation { from: 0.9; to: 1.7; duration: 1500; easing.type: Easing.OutQuad }
            }
            SequentialAnimation on opacity {
                running: root.pulsing
                loops: Animation.Infinite
                PauseAnimation { duration: index * 500 }
                NumberAnimation { from: 0.7; to: 0; duration: 1500; easing.type: Easing.OutQuad }
            }
        }
    }
    Image {
        anchors.fill: parent
        source: Theme.art(root.kind === "generic" ? "generic" : root.kind + "-base")
        sourceSize: Qt.size(480, 300)
        smooth: true
    }
    Image {
        visible: root.kind === "case" || root.kind === "aio" || root.kind === "pump"
        anchors.fill: parent
        source: !visible ? "" : Theme.art(root.kind === "pump" ? "pump-ring-" + (root.active ? "active" : "idle")
                                               : root.kind + "-rotor-" + (root.active ? "active" : "idle"))
        sourceSize: Qt.size(480, 300)
        smooth: true
        transform: Rotation { origin.x: root.centre.x; origin.y: root.centre.y; angle: root.angle }
    }
    FrameAnimation {
        running: root.visible && root.rpm > 0 && root.kind !== "generic"
        onTriggered: {
            const degPerSec = root.kind === "pump" ? 25 + root.rpm * 0.01 : root.rpm * 0.12
            root.angle = (root.angle + frameTime * degPerSec) % 360
        }
    }
}
