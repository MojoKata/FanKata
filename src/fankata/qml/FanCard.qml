import QtQuick
import "."

// A Fan tile. Designed at 380 × 290 and scaled as a whole by `u` (requirement 5.2.5):
// every size, font and stroke is multiplied by it, so the contents scale with the
// tile rather than just stretching.
Rectangle {
    id: card
    property var fan: null
    property bool selected: false
    property bool lifted: false          // being dragged
    readonly property real baseWidth: 380
    readonly property real baseHeight: 290
    readonly property real u: width / baseWidth
    signal clicked()
    height: baseHeight * u
    radius: 18 * u
    color: Theme.surface
    border.width: selected ? 2 : 1
    border.color: selected ? Theme.accent : hover.hovered || lifted ? Theme.borderStrong : Theme.border
    readonly property bool managed: !!fan && fan.managed
    readonly property bool warning: !!fan && fan.status === "warning"
    function px(v) { return Math.round(v * u) }       // whole-pixel font sizes

    Rectangle {      // soft shadow
        z: -1; anchors.fill: parent
        radius: card.radius; color: "#000000"; opacity: card.lifted ? (Theme.dark ? 0.55 : 0.18) : (Theme.dark ? 0.28 : 0.05)
        anchors.topMargin: (card.lifted ? 10 : 3) * card.u; anchors.bottomMargin: (card.lifted ? -14 : -3) * card.u
    }
    Rectangle {
        id: illus
        x: 10 * card.u; y: 10 * card.u; width: parent.width - 20 * card.u; height: 134 * card.u; radius: 12 * card.u
        clip: true
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: card.managed ? Theme.illusA : Theme.illusOff }
            GradientStop { position: 1; color: card.managed ? Theme.illusB : Theme.illusOff }
        }
        FanArt {
            fan: card.fan
            scale: card.u
            x: (parent.width - width) / 2 + (badge.visible ? 36 * card.u : 0)
            Behavior on x { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
            y: (parent.height - height) / 2
        }
        // No "Managed" badge on tiles: the Probe group already says so (requirement 5.2.4).
        Pill {
            id: badge
            u: card.u
            visible: !card.managed || card.warning || (card.fan && (card.fan.pulsing || card.fan.status === "restoring"))
            x: 12 * card.u; y: 12 * card.u
            text: card.fan && card.fan.pulsing ? "Speed pulse" : card.fan && card.fan.status === "restoring" ? "Returning to system default…" : card.warning ? "Attention" : card.managed ? "Managed" : "System default"
            showDot: true
            color: card.fan && card.fan.pulsing ? Theme.accentSoft : card.warning ? Theme.warnSoft : card.managed ? Theme.okSoft : (Theme.dark ? "#2a2e39" : "#e8eaf0")
            fg: card.fan && card.fan.pulsing ? Theme.accent : card.warning ? Theme.warn : card.managed ? Theme.ok : Theme.muted
            dot: fg === Theme.muted ? Theme.faint : fg
        }
    }
    Column {
        x: 22 * card.u; y: 156 * card.u
        width: parent.width - 110 * card.u
        spacing: 4 * card.u
        Text { text: card.fan ? card.fan.name : ""; color: Theme.text; font.pixelSize: card.px(17); font.bold: true; elide: Text.ElideRight; width: parent.width }
        Text { text: card.fan ? card.fan.driver_label : ""; color: Theme.muted; font.pixelSize: card.px(12); font.family: Theme.mono; elide: Text.ElideRight; width: parent.width }
    }
    DutyRing {
        x: parent.width - 70 * card.u; y: 158 * card.u
        width: 48 * card.u; height: 48 * card.u
        value: card.fan ? card.fan.duty : null
        active: card.managed
    }
    Row {
        x: 22 * card.u; y: 206 * card.u
        spacing: 8 * card.u
        Icon { name: "fan"; size: 16 * card.u; color: card.managed ? Theme.accent : Theme.faint; anchors.verticalCenter: parent.verticalCenter }
        Text {
            id: rpmText
            visible: card.fan && card.fan.rpm !== null && card.fan.rpm !== undefined
            text: card.fan ? Theme.thousands(card.fan.rpm) : ""
            color: Theme.text; font.pixelSize: card.px(20); font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: card.fan && card.fan.rpm !== null && card.fan.rpm !== undefined
            text: "RPM"; color: Theme.muted; font.pixelSize: card.px(12); font.bold: true
            anchors.baseline: rpmText.baseline
        }
        Text {
            visible: !card.fan || card.fan.rpm === null || card.fan.rpm === undefined
            text: "Speed unknown"; color: Theme.faint; font.pixelSize: card.px(14)
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    Rectangle { x: 18 * card.u; y: parent.height - 50 * card.u; width: parent.width - 36 * card.u; height: 1; color: Theme.border }
    Item {
        x: 18 * card.u; y: parent.height - 49 * card.u; width: parent.width - 36 * card.u; height: 49 * card.u
        // managed: curve thumbnail + name
        Row {
            visible: !!card.fan && !!card.fan.curve
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10 * card.u
            Rectangle {
                width: 56 * card.u; height: 30 * card.u; radius: 7 * card.u; color: Theme.input
                CurveChart {
                    anchors.fill: parent; anchors.margins: 4 * card.u
                    points: card.fan ? card.fan.curve_points : []
                    labels: false; markers: false; lineWidth: 2 * card.u; background: Theme.input
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: card.fan && card.fan.curve ? card.fan.curve : ""; color: Theme.text; font.pixelSize: card.px(13); font.bold: true }
                Text { text: "curve"; color: Theme.muted; font.pixelSize: card.px(11) }
            }
        }
        Text {
            visible: !!card.fan && !!card.fan.curve && !card.fan.probe
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            text: "Choose a probe"; color: Theme.warn; font.pixelSize: card.px(13); font.bold: true
        }
        Text {
            visible: !!card.fan && !card.fan.curve
            anchors.verticalCenter: parent.verticalCenter; x: 4 * card.u
            text: "Not managed"; color: Theme.muted; font.pixelSize: card.px(13)
        }
        Row {
            visible: !!card.fan && !card.fan.curve
            anchors.right: parent.right; anchors.rightMargin: 2 * card.u
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4 * card.u
            Text { text: "Assign a curve"; color: Theme.accent; font.pixelSize: card.px(13); font.bold: true; anchors.verticalCenter: parent.verticalCenter }
            Icon { name: "chevRight"; size: 14 * card.u; lineWidth: 1.8 * card.u; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
        }
    }
    // pointer handlers (not a MouseArea) so a tap selects and a drag moves the tile
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: card.clicked() }
}
