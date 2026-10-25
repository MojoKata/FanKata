import QtQuick
import "."

Item {
    id: root
    property string selected: ""
    signal message(string text)
    property alias editor: editor
    property alias dialog: dialog
    property alias probes: probes
    readonly property var curve: {
        for (const c of backend.curves) if (c.name === selected) return c
        return backend.curves.length ? backend.curves[0] : null
    }
    readonly property bool probesOpen: backend.prefs.probesPanelOpen !== false

    Rectangle {
        id: gallery
        width: 300; height: parent.height; color: Theme.side
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
        Text { id: galleryTitle; x: 24; y: 26; text: "Curves"; color: Theme.text; font.pixelSize: 20; font.bold: true }
        Text { anchors.left: galleryTitle.right; anchors.leftMargin: 8; anchors.baseline: galleryTitle.baseline; text: backend.curves.length; color: Theme.faint; font.pixelSize: 14 }
        FButton {
            anchors.right: parent.right; anchors.rightMargin: 24; y: 18; implicitHeight: 32
            text: "New"; icon: "plus"; enabledButton: backend.connected
            onClicked: { const n = backend.newCurve(); if (n) root.selected = n }
        }
        ListView {
            anchors.fill: parent; anchors.topMargin: 66
            clip: true; spacing: 12
            boundsBehavior: Flickable.StopAtBounds
            model: backend.curves
            header: Item { height: 0 }
            footer: Item { height: 16 }
            delegate: Item {
                width: ListView.view.width; height: 100
                CurveCard {
                    x: 20
                    curve: modelData
                    selected: root.curve && modelData.name === root.curve.name
                    onClicked: root.selected = modelData.name
                }
            }
        }
    }
    CurveEditor {
        id: editor
        anchors.left: gallery.right; anchors.leftMargin: 32
        anchors.right: probes.left; anchors.rightMargin: 32
        height: parent.height
        visible: root.curve !== null
        curve: root.curve
        onMessage: text => root.message(text)
        onRenamed: name => root.selected = name
        onDeleted: root.selected = ""
    }
    Text {
        visible: root.curve === null
        anchors.centerIn: editor
        text: "No curves yet. Create one with New."
        color: Theme.muted; font.pixelSize: 14
    }
    ProbesPanel {
        id: probes
        anchors.right: parent.right
        width: root.probesOpen ? 320 : 56
        height: parent.height
        open: root.probesOpen
        onToggle: backend.setPref("probesPanelOpen", !root.probesOpen)
        onNewProbe: dialog.openFor("")
        onEditProbe: name => dialog.openFor(name)
    }
    ProbeDialog {
        id: dialog
        onMessage: text => root.message(text)
    }
}
