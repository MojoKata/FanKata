import QtQuick
import QtQuick.Controls.Basic
import "."

Rectangle {
    id: root
    property var fan: null
    signal closeRequested()
    signal message(string text)
    color: Theme.surface
    readonly property bool pulsing: !!fan && fan.pulsing
    readonly property var result: backend.lastPulse && fan && backend.lastPulse.fan === fan.id ? backend.lastPulse : null
    readonly property bool warning: !!fan && fan.status === "warning"
    property alias menu: fanMenu          // for the screenshot tour

    Rectangle { width: 1; height: parent.height; color: Theme.border }
    Rectangle {      // shadow towards the grid
        z: -1; x: -10; width: 10; height: parent.height
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 1; color: Theme.alpha("#000000", Theme.dark ? 0.25 : 0.05) }
        }
    }

    function restoreText(r) {
        if (!r) return ""
        if (r.mode === "auto") return "Automatic (firmware control)"
        if (r.mode === "fixed") return "Fixed at " + r.duty + " %"
        return "Full speed"
    }

    Flickable {
        id: detailFlick
        anchors.fill: parent
        contentHeight: col.height + 40
        clip: true
        layer.enabled: GraphicsInfo.api === GraphicsInfo.Software   // clips Shape icons
        Rectangle { z: -1; width: parent.width; height: Math.max(detailFlick.height, col.height + 40); color: Theme.surface }
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: col
            x: 28; y: 16
            width: root.width - 56
            spacing: 0

            Item {
                width: parent.width; height: 34
                Text { anchors.verticalCenter: parent.verticalCenter; text: "FAN DETAILS"; color: Theme.faint; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2 }
                IconButton {
                    id: menuButton
                    anchors.right: closeButton.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                    round: true; icon: "dots"; iconSize: 14; lineWidth: 1.6
                    active: fanMenu.visible
                    onClicked: fanMenu.visible ? fanMenu.close() : fanMenu.open()
                }
                IconButton {
                    id: closeButton
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    round: true; icon: "x"
                    onClicked: root.closeRequested()
                }
                PopMenu {
                    id: fanMenu
                    menuWidth: 300
                    x: parent.width - menuWidth
                    y: 40
                    items: [{ key: "pulse", text: "Speed pulse (8 sec)", subtext: "Spot this fan by ramping its speed",
                              icon: "pulse", type: "action", enabled: backend.connected }]
                    onTriggered: key => { if (key === "pulse") backend.startPulse(root.fan.id) }
                }
            }
            Item { width: 1; height: 10 }
            Rectangle {
                width: parent.width; height: 118; radius: 14
                clip: true
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: root.fan && (root.fan.managed || root.pulsing) ? Theme.illusA : Theme.illusOff }
                    GradientStop { position: 1; color: root.fan && (root.fan.managed || root.pulsing) ? Theme.illusB : Theme.illusOff }
                }
                FanArt { fan: root.fan; x: (parent.width - width) / 2; y: (parent.height - height) / 2 }
                Pill {     // no "Managed" badge (requirement 5.4.8)
                    visible: root.pulsing || root.warning || !(root.fan && root.fan.managed) || (root.fan && root.fan.status === "restoring")
                    x: 12; y: 12
                    text: root.pulsing ? "Speed pulse" : root.fan && root.fan.status === "restoring" ? "Returning to system default…" : root.warning ? "Attention" : root.fan && root.fan.managed ? "Managed" : "System default"
                    showDot: true
                    color: root.pulsing ? Theme.accentSoft : root.warning ? Theme.warnSoft : root.fan && root.fan.managed ? Theme.okSoft : (Theme.dark ? "#2a2e39" : "#e8eaf0")
                    fg: root.pulsing ? Theme.accent : root.warning ? Theme.warn : root.fan && root.fan.managed ? Theme.ok : Theme.muted
                    dot: fg === Theme.muted ? Theme.faint : fg
                }
            }
            Item { width: 1; height: 14 }
            Item {
                width: parent.width; height: 50
                Row {
                    visible: !nameEdit.visible
                    spacing: 10
                    Text { id: nameText; text: root.fan ? root.fan.name : ""; color: Theme.text; font.pixelSize: 22; font.bold: true; elide: Text.ElideRight; width: Math.min(implicitWidth, 230) }
                    Icon {
                        anchors.verticalCenter: nameText.verticalCenter; name: "pencil"; size: 15; color: Theme.muted
                        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: { nameEdit.text = root.fan.name; nameEdit.visible = true; nameEdit.forceActiveFocus(); nameEdit.selectAll() } }
                    }
                }
                TextField {
                    id: nameEdit
                    visible: false
                    width: 240; height: 34
                    font.pixelSize: 18; font.bold: true
                    color: Theme.text
                    background: Rectangle { radius: 8; color: Theme.input; border.color: Theme.accent; border.width: 2 }
                    onAccepted: { const e = backend.renameFan(root.fan.id, text); if (e) root.message(e); visible = false }
                    onActiveFocusChanged: if (!activeFocus && visible) accepted()
                    Keys.onEscapePressed: visible = false
                }
                Text {
                    y: 30
                    text: root.fan ? root.fan.chip + " · " + (root.fan.rpm_sensor ? root.fan.rpm_sensor.split(":")[1] + "_input · " : "") + "pwm" + root.fan.index : ""
                    color: Theme.muted; font.pixelSize: 12; font.family: Theme.mono
                }
                Rectangle {
                    id: typeButton
                    anchors.right: parent.right; y: 2
                    height: 28; radius: 14; color: Theme.input; border.color: Theme.border
                    width: typeRow.implicitWidth + 24
                    Row {
                        id: typeRow
                        anchors.centerIn: parent
                        spacing: 6
                        Text {
                            text: root.fan ? root.fan.type_label + (root.fan.type_overridden ? "" : " · detected") : ""
                            color: Theme.muted; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter
                        }
                        Icon { name: "chevDown"; size: 12; color: Theme.muted; anchors.verticalCenter: parent.verticalCenter }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: typeMenu.open() }
                    PopMenu {
                        id: typeMenu
                        menuWidth: 240
                        x: typeButton.width - menuWidth; y: 34
                        items: root.fan ? [["case", "Case fan"], ["aio", "AIO cooler fan"], ["pump", "Pump"], ["generic", "Generic PWM header"]].map(t => ({
                            key: t[0], type: "radio", checked: root.fan.type === t[0],
                            text: t[1] + (root.fan.detected_type === t[0] ? " · detected" : "") })) : []
                        onTriggered: key => { const e = backend.setFanType(root.fan.id, key); if (e) root.message(e) }
                    }
                }
            }
            Item { width: 1; height: 12 }
            Row {
                spacing: 8
                Repeater {
                    model: root.fan ? [
                        [root.fan.rpm === null || root.fan.rpm === undefined ? "—" : Theme.thousands(root.fan.rpm), "RPM", false],
                        [root.fan.duty === null || root.fan.duty === undefined ? "—" : root.fan.duty + " %", "duty cycle", false],
                        [root.fan.probe ? Theme.fmt1(root.fan.probe_value) + " °C" : "—", root.fan.probe || "no probe", true]] : []
                    Rectangle {
                        width: (col.width - 16) / 3; height: 60; radius: 12; color: Theme.input
                        Text { x: 14; y: 12; text: modelData[0]; font.pixelSize: 19; font.bold: true
                               color: modelData[2] && root.fan.probe_value !== null && root.fan.probe_value !== undefined ? Theme.heat(root.fan.probe_value) : Theme.text }
                        Text { x: 14; y: 38; text: modelData[1]; font.pixelSize: 12; color: Theme.muted; font.family: modelData[2] ? Theme.mono : Qt.application.font.family
                               width: parent.width - 20; elide: Text.ElideRight }
                    }
                }
            }
            Item { width: 1; height: 18 }
            Item {
                width: parent.width; height: 22
                Text { text: "Curve"; color: Theme.text; font.pixelSize: 13; font.bold: true }
                Text { anchors.right: parent.right; text: "Clear to return to system default"; color: Theme.faint; font.pixelSize: 12 }
            }
            Select {
                width: parent.width
                enabledSelect: !root.pulsing && backend.connected
                clearable: true
                placeholder: "Not managed — choose a curve"
                current: root.fan && root.fan.curve ? root.fan.curve : ""
                model: backend.curves.map(c => ({ key: c.name, title: c.name, subtitle: c.points.length + " points", points: c.points }))
                onPicked: key => { const e = backend.setFanCurve(root.fan.id, key); if (e) root.message(e) }
                onCleared: { const e = backend.setFanCurve(root.fan.id, ""); if (e) root.message(e) }
            }
            Item { width: 1; height: 12 }
            Text { text: "Probe"; color: Theme.text; font.pixelSize: 13; font.bold: true; height: 22 }
            Select {
                width: parent.width
                enabledSelect: !root.pulsing && backend.connected && !!root.fan && !!root.fan.curve
                placeholder: root.fan && root.fan.curve ? "Choose a probe" : "Choose a curve first"
                current: root.fan && root.fan.probe ? root.fan.probe : ""
                model: backend.probes.map(p => ({ key: p.name, title: p.name, mono: true, value: p.value,
                                                  subtitle: p.kind === "custom" ? p.expr : p.desc }))
                onPicked: key => { const e = backend.setFanProbe(root.fan.id, key); if (e) root.message(e) }
            }
            Item { width: 1; height: 10 }
            Row {
                spacing: 6
                Icon { name: root.warning ? "warn" : "info"; size: 14; color: root.warning ? Theme.warn : Theme.faint; anchors.verticalCenter: parent.verticalCenter }
                Text {
                    width: col.width - 20
                    wrapMode: Text.WordWrap
                    text: root.warning && root.fan.message ? root.fan.message
                          : "When unmanaged: " + root.restoreText(root.fan ? root.fan.restore : null)
                    color: root.warning ? Theme.warn : Theme.faint; font.pixelSize: 12
                }
            }
            Item { width: 1; height: 12 }

            // live curve chart, speed pulse, or pulse result
            Rectangle {
                width: parent.width; height: 206; radius: 14; color: Theme.input
                visible: !root.pulsing && !root.result
                Row {
                    x: 16; y: 16; spacing: 8
                    Text { text: "Live"; color: Theme.text; font.pixelSize: 13; font.bold: true }
                    Rectangle { width: 8; height: 8; radius: 4; color: backend.connected ? Theme.ok : Theme.faint; anchors.verticalCenter: parent.verticalCenter }
                }
                Text {
                    anchors.right: parent.right; anchors.rightMargin: 16; y: 16
                    visible: !!root.fan && !!root.fan.curve && root.fan.probe_value !== null && root.fan.probe_value !== undefined
                    text: root.fan && root.fan.probe_value !== null && root.fan.probe_value !== undefined
                          ? Theme.fmt1(root.fan.probe_value) + " °C  →  " + root.fan.duty + " %" : ""
                    color: root.fan && root.fan.probe_value !== null && root.fan.probe_value !== undefined ? Theme.heat(root.fan.probe_value) : Theme.muted
                    font.pixelSize: 13; font.bold: true
                }
                CurveChart {
                    visible: !!root.fan && !!root.fan.curve
                    x: 4; y: 34; width: parent.width - 12; height: 168
                    points: root.fan ? root.fan.curve_points : []
                    allowZero: root.fan ? root.fan.curve_allow_zero : false
                    showFloor: false
                    markerRadius: 4; lineWidth: 2.6; background: Theme.input
                    ops: root.fan && root.fan.probe ? [{ v: root.fan.probe_value }] : []
                    opsLabels: false
                }
                Text {
                    visible: !root.fan || !root.fan.curve
                    anchors.centerIn: parent
                    width: parent.width - 60; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                    text: "Choose a curve and a probe to let Fankata control this fan."
                    color: Theme.faint; font.pixelSize: 13
                }
            }
            Rectangle {
                width: parent.width; height: 206; radius: 14; color: Theme.input
                visible: root.pulsing || !!root.result
                Rectangle { x: 16; y: 18; width: 8; height: 8; radius: 4; color: root.pulsing ? Theme.accent : Theme.faint }
                Rectangle { visible: root.pulsing; x: 12; y: 14; width: 16; height: 16; radius: 8; color: Theme.accent; opacity: 0.25 }
                Text {
                    id: pulseTitle
                    x: 34; y: 14
                    text: "Speed pulse"; color: Theme.text; font.pixelSize: 13; font.bold: true
                }
                Text {
                    anchors.left: pulseTitle.right; anchors.leftMargin: 10; anchors.baseline: pulseTitle.baseline
                    text: root.pulsing && backend.pulse ? Math.max(0, Math.ceil(backend.pulse.length - backend.pulse.elapsed)) + " s left"
                          : root.result && root.result.stopped && root.result.stopped !== "done" ? "stopped" : "finished"
                    color: Theme.muted; font.pixelSize: 13
                }
                FButton {
                    anchors.right: parent.right; anchors.rightMargin: 12; y: 8; implicitHeight: 30
                    text: root.pulsing ? "Stop" : "Dismiss"
                    danger: root.pulsing
                    onClicked: root.pulsing ? backend.stopPulse() : backend.dismissPulseResult()
                }
                PulseChart {
                    x: 6; y: 44; width: parent.width - 16; height: 124
                    pulse: root.pulsing ? backend.pulse : root.result
                    finished: !root.pulsing
                }
                Row {
                    x: 14; y: parent.height - 32
                    spacing: 8
                    visible: !!root.result
                    readonly property string kind: root.result ? root.result.kind : ""
                    Rectangle {
                        width: 18; height: 18; radius: 9; anchors.verticalCenter: parent.verticalCenter
                        color: parent.kind === "self" ? Theme.okSoft : Theme.warnSoft
                        Icon { anchors.centerIn: parent; name: parent.parent.kind === "self" ? "check" : "warn"; size: 12; lineWidth: 2; color: parent.parent.kind === "self" ? Theme.ok : Theme.warn }
                    }
                    Text {
                        width: col.width - 50; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.result ? root.result.message : ""
                        color: parent.kind === "self" ? Theme.ok : Theme.warn; font.pixelSize: 12; font.bold: true
                    }
                }
                Text {
                    visible: root.pulsing
                    x: 16; y: parent.height - 30; width: parent.width - 32; elide: Text.ElideRight
                    text: "Listen and look: the fan speeds up and slows down every second."
                    color: Theme.muted; font.pixelSize: 12
                }
            }
        }
    }
}
