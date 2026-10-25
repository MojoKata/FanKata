import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import "."

ApplicationWindow {
    id: win
    width: 1280
    height: 800
    minimumWidth: 960
    minimumHeight: 640
    visible: true
    title: "Fankata"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: Theme.bg
    property string view: "fans"
    property alias fans: fansView
    property alias curves: curvesView

    Component.onCompleted: Theme.mode = themeOverride || backend.prefs.theme || "system"
    Connections {
        target: backend
        function onPrefsChanged() { if (!themeOverride) Theme.mode = backend.prefs.theme || "system" }
        function onToast(kind, text) { toast.show(kind, text) }
    }

    HeaderBar {
        id: header
        width: parent.width
        z: 10
        window: win
        view: win.view
        onViewSelected: v => win.view = v
        onAbout: about.open()
        onTroubleshoot: troubleshootDialog.openDialog()
    }
    Rectangle {
        id: banner
        visible: backend.readOnly
        anchors.top: header.bottom
        width: parent.width; height: visible ? 44 : 0
        color: Theme.warnSoft
        Row {
            anchors.centerIn: parent; spacing: 12
            Icon { name: "warn"; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: backend.serviceBusy ? "Turning fan control on…"
                      : Qt.platform.os === "windows"
                        ? "Fan control is off: fans are under firmware control."    // readings need the service's driver
                        : "Fan control is off: fans are under firmware control, and Fankata is showing live readings only."
                color: Theme.warn; font.pixelSize: 13; font.bold: true
            }
            FButton {
                visible: !backend.serviceBusy
                anchors.verticalCenter: parent.verticalCenter
                implicitHeight: 28
                text: "Turn on"; icon: "check"
                onClicked: backend.setServiceEnabled(true)
            }
        }
    }
    Item {
        id: body
        anchors.top: banner.bottom; anchors.bottom: parent.bottom
        width: parent.width
        FansView {
            id: fansView
            objectName: "fansView"
            anchors.fill: parent
            visible: win.view === "fans"
            onMessage: text => toast.show("error", text)
            onTroubleshootRequested: troubleshootDialog.openDialog()
        }
        CurvesView {
            id: curvesView
            anchors.fill: parent
            visible: win.view === "curves"
            onMessage: text => toast.show("error", text)
        }
    }
    TroubleshootDialog { id: troubleshootDialog }
    Toast { id: toast; z: 20 }
    Popup {
        id: about
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 380; padding: 28
        Overlay.modal: Rectangle { color: Theme.scrim }
        background: Rectangle { radius: 20; color: Theme.surface; border.color: Theme.border }
        contentItem: Column {
            spacing: 10
            Image { source: "assets/art/fankata.svg"; width: 64; height: 64; sourceSize: Qt.size(128, 128) }
            Text { text: "Fankata " + appVersion; color: Theme.text; font.pixelSize: 20; font.bold: true }
            Text { width: 324; wrapMode: Text.WordWrap; color: Theme.muted; font.pixelSize: 13
                   text: "Fan control for Linux and Windows: Curves link Probes to Fans. Changes are applied by the fankatad service, which keeps running when this window is closed." }
            FButton { text: "Close"; onClicked: about.close() }
        }
    }
    ResizeHandles { window: win }

    // --- hooks for the screenshot tour ---------------------------------------------
    function fanId(name) { const f = backend.fans.find(x => x.name === name); return f ? f.id : "" }
    function tour(step) {
        fansView.detail.menu.close(); curvesView.editor.menu.close(); curvesView.dialog.close(); fansView.demoDragEnd()
        header.menu.close(); troubleshootDialog.grub.close()
        if (!step.troubleshoot) troubleshootDialog.close()
        const size = step.size || [1280, 800]
        if (width !== size[0] || height !== size[1]) { width = size[0]; height = size[1] }
        curvesView.editor.chart.setHover(""); curvesView.editor.table.clearError()
        if (step.view) view = step.view
        if (step.fan !== undefined) fansView.selected = step.fan ? fanId(step.fan) : ""
        fansView.scrollTo(0)
        if (step.curve) curvesView.selected = step.curve
        if (step.probesOpen !== undefined) backend.setPref("probesPanelOpen", step.probesOpen)
        if (step.fanMenu) fansView.detail.menu.open()
        if (step.appMenu) header.menu.open()
        if (step.drag) fansView.demoDrag(step.drag[0], step.drag[1], step.drag[2], step.drag[3], step.drag[4], step.drag[5])
        if (step.curveMenu) curvesView.editor.menu.open()
        if (step.hoverAdd) curvesView.editor.chart.setHover("add", step.hoverAdd[0], step.hoverAdd[1])
        if (step.hoverRemove !== undefined) curvesView.editor.chart.setHover("remove", step.hoverRemove)
        if (step.tableError) curvesView.editor.table.showError(step.tableError[0], step.tableError[1], step.tableError[2])
        if (step.troubleshoot && !troubleshootDialog.visible) troubleshootDialog.openDialog()
        if (step.tipsOpen) troubleshootDialog.tipsOpen = true
        if (step.probe) { curvesView.dialog.openFor(""); curvesView.dialog.setDemo(step.probe[0], step.probe[1]) }
    }
}
