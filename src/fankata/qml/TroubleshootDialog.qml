import QtQuick
import QtQuick.Controls.Basic
import "."
import "Markdown.js" as Md

// Troubleshoot fans (requirement 4.7): summary, checks with fixes, then "Things to try".
Popup {
    id: root
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    // sized from the window: the overlay has no size yet on some platforms (Windows) before it opens
    readonly property var win: ApplicationWindow.window
    width: Math.min(780, (win && win.width > 0 ? win.width : 1280) - 40)
    height: Math.min(712, (win && win.height > 0 ? win.height : 800) - 40)
    padding: 0
    closePolicy: Popup.CloseOnEscape
    Overlay.modal: Rectangle { color: Theme.scrim }
    background: Rectangle {
        radius: 20; color: Theme.surface; border.color: Theme.border
        Rectangle { z: -1; anchors.fill: parent; anchors.topMargin: 8; anchors.bottomMargin: -8; radius: 20; color: "#000000"; opacity: Theme.dark ? 0.4 : 0.12 }
    }
    readonly property var r: troubleshoot ? troubleshoot.result : ({})
    readonly property var checks: r.checks || []
    readonly property string busy: troubleshoot ? troubleshoot.busy : ""
    property bool tipsOpen: false
    property alias grub: grubDialog
    property alias flick: flick

    function openDialog() { tipsOpen = false; open(); troubleshoot.run() }
    function rich(s) { return Md.inline(s || "", { mono: Theme.mono, codeBg: Theme.track, code: Theme.text, link: Theme.accent }) }

    Connections {
        target: troubleshoot
        function onChanged() { if (troubleshoot.result.tips_open) root.tipsOpen = true }
        function onGrubRequested(preview) { grubDialog.openFor(preview) }
    }
    Connections {
        target: backend
        function onConnectionChanged() { if (root.visible) troubleshoot.run() }
    }

    contentItem: Item {
        Item {
            id: head
            x: 30; y: 28; width: parent.width - 60; height: 54
            Icon { y: 3; name: "lifebuoy"; size: 22; lineWidth: 1.8; color: Theme.accent }
            Text { x: 34; text: "Troubleshoot fans"; color: Theme.text; font.pixelSize: 21; font.bold: true }
            Text { y: 36; text: root.r.lead || ""; color: Theme.muted; font.pixelSize: 13 }
            IconButton { anchors.right: parent.right; y: -2; round: true; icon: "x"; onClicked: root.close() }
        }
        Rectangle {
            id: strip
            x: 30; anchors.top: head.bottom; anchors.topMargin: 12
            width: parent.width - 60; height: 62; radius: 14; color: Theme.illusA
            Row {
                anchors.fill: parent
                Repeater {
                    model: root.r.summary || []
                    Item {
                        width: strip.width / 3; height: strip.height
                        Rectangle { visible: index > 0; y: 14; width: 1; height: 34; color: Theme.border }
                        Column {
                            x: 20; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            width: parent.width - 30
                            Text { width: parent.width; elide: Text.ElideRight; text: modelData[0]; color: Theme.text; font.pixelSize: 15; font.bold: true }
                            Text { width: parent.width; elide: Text.ElideRight; text: modelData[1]; color: Theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
            }
            Text {
                visible: !root.r.summary
                anchors.centerIn: parent; text: "Checking this PC…"; color: Theme.muted; font.pixelSize: 13
            }
        }
        Flickable {
            id: flick
            x: 30; width: parent.width - 60
            anchors.top: strip.bottom; anchors.topMargin: 16
            anchors.bottom: footer.top; anchors.bottomMargin: 12
            contentHeight: body.height + 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }
            Column {
                id: body
                width: flick.width
                spacing: 0
                Text { text: "CHECKS"; color: Theme.faint; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2; bottomPadding: 10 }
                Repeater {
                    model: root.checks
                    delegate: CheckRow { width: body.width; c: modelData; first: index === 0 }
                }
                Item { width: 1; height: 8 }
                Rectangle { width: body.width; height: 1; color: Theme.border }
                Item {
                    id: tipsHead
                    width: body.width; height: 46
                    Icon { y: 15; name: root.tipsOpen ? "chevDown" : "chevRight"; color: Theme.muted }
                    Text { id: tt; x: 24; y: 12; text: "Things to try"; color: Theme.text; font.pixelSize: 15; font.bold: true }
                    Text {
                        x: tt.x + tt.width + 10; y: 14
                        text: root.r.tips_note || ((root.r.tips_count || 0) + " suggestions for " + (root.r.platform === "windows" ? "Windows" : "Linux"))
                        color: Theme.muted; font.pixelSize: 13
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.tipsOpen = !root.tipsOpen }
                }
                Column {
                    visible: root.tipsOpen
                    width: body.width
                    spacing: 6
                    Repeater {
                        model: root.r.tips || []
                        Loader {
                            width: body.width
                            sourceComponent: modelData.kind === "code" ? codeBlock : modelData.kind === "h" ? heading : para
                            property var blk: modelData
                        }
                    }
                }
            }
        }
        Item {
            id: footer
            anchors.bottom: parent.bottom; width: parent.width; height: 74
            Rectangle { width: parent.width; height: 1; color: Theme.border }
            FButton { x: 30; y: 18; implicitHeight: 38; text: "Copy report"; icon: "copy"; enabledButton: !!root.r.summary; onClicked: troubleshoot.copyReport() }
            Row {
                anchors.right: parent.right; anchors.rightMargin: 30; y: 18; spacing: 10
                FButton {
                    implicitHeight: 38; icon: "refresh"
                    text: root.busy === "gather" ? "Checking…" : "Run again"
                    enabledButton: root.busy === ""
                    onClicked: troubleshoot.run()
                }
                FButton { implicitHeight: 38; text: "Close"; primary: true; onClicked: root.close() }
            }
        }
    }

    // --- pieces ----------------------------------------------------------------------
    component Badge: Rectangle {
        property string st
        width: 26; height: 26; radius: 13
        color: ({ ok: Theme.okSoft, warn: Theme.warnSoft, fail: Theme.errSoft, info: Theme.accentSoft })[st] || Theme.track
        readonly property color fg: ({ ok: Theme.ok, warn: Theme.warn, fail: Theme.err, info: Theme.accent })[st] || Theme.faint
        Icon {
            anchors.centerIn: parent; visible: parent.st !== "wait"
            size: parent.st === "fail" ? 12 : 14; lineWidth: parent.st === "info" ? 1.8 : 2.2; color: parent.fg
            name: ({ ok: "check", warn: "bang", fail: "x", info: "info" })[parent.st] || ""
        }
        Rectangle { anchors.centerIn: parent; visible: parent.st === "wait"; width: 6; height: 6; radius: 3; color: parent.fg }
    }
    component CodeBox: Rectangle {
        property var lines: []
        height: codeText.height + 22
        radius: 10; color: Theme.input; border.color: Theme.border
        Text {
            id: codeText
            x: 14; y: 11; width: parent.width - 110
            text: lines.join("\n"); color: Theme.text; font.family: Theme.mono; font.pixelSize: 12; lineHeight: 1.25
            wrapMode: Text.WrapAnywhere
        }
        FButton {
            anchors.right: parent.right; anchors.rightMargin: 7; y: 7; implicitHeight: 26
            text: "Copy"; icon: "copy"
            onClicked: { troubleshoot.copyText(parent.lines.join("\n") + "\n"); backend.toast("info", "Copied.") }
        }
    }
    component CheckRow: Item {
        id: row
        property var c
        property bool first: false
        readonly property var act: c.action || null
        height: Math.max(40, col.height) + (first ? 4 : 18)
        Rectangle { visible: !row.first; x: 44; width: parent.width - 44; height: 1; color: Theme.border }
        Badge { x: 3; y: (row.first ? 0 : 14) + 2; st: row.c.st }
        Column {
            id: col
            x: 44; y: row.first ? 0 : 14
            width: row.width - 44 - (btn.visible ? btn.width + 16 : 0)
            spacing: 6
            Row {
                spacing: 10
                Text { text: row.c.title; color: row.c.st === "wait" && !row.c.tag ? Theme.muted : Theme.text; font.pixelSize: 14; font.bold: true }
                Rectangle {
                    visible: !!row.c.tag
                    width: tagText.width + 18; height: 20; radius: 10; color: Theme.track
                    Text { id: tagText; anchors.centerIn: parent; text: row.c.tag || ""; color: Theme.muted; font.pixelSize: 11; font.bold: true }
                }
            }
            Text {
                visible: !!row.c.detail
                width: parent.width; wrapMode: Text.WordWrap; textFormat: Text.RichText
                text: root.rich(row.c.detail); color: Theme.muted; font.pixelSize: 13; lineHeight: 1.2
                onLinkActivated: link => Qt.openUrlExternally(link)
            }
            Item {
                visible: !!row.c.check
                width: parent.width; height: Math.max(20, chkText.height)
                Rectangle {
                    id: box
                    y: 1; width: 18; height: 18; radius: 5
                    color: root.r.persist ? Theme.accent : "transparent"
                    border.width: root.r.persist ? 0 : 1.6; border.color: Theme.borderStrong
                    Icon { anchors.centerIn: parent; visible: !!root.r.persist; name: "check"; size: 12; lineWidth: 2.2; color: "#ffffff" }
                }
                Text {
                    id: chkText
                    x: 28; width: parent.width - 28; wrapMode: Text.WordWrap; textFormat: Text.RichText
                    text: root.rich(row.c.check ? row.c.check.label : ""); color: Theme.text; font.pixelSize: 13
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: troubleshoot.setPersist(!root.r.persist) }
            }
            CodeBox { visible: !!row.c.code; width: row.width - 44; lines: row.c.code || [] }
        }
        FButton {
            id: btn
            visible: !!row.act
            anchors.right: parent.right; y: row.first ? 0 : 14
            implicitHeight: 32
            readonly property bool running: !!row.act && root.busy === row.act.id
            text: running ? (row.act.id === "scan" ? "Scanning…" : "Working…") : (row.act ? row.act.label : "")
            icon: !row.act ? "" : row.act.lock ? "lock" : (row.act.icon || "")
            primary: !!row.act && !!row.act.primary
            enabledButton: !!row.act && !row.act.disabled && root.busy === ""
            onClicked: troubleshoot.act(row.act.id)
        }
    }
    Component {
        id: para
        Item {
            height: pText.height + 4
            Rectangle { visible: blk.kind === "li"; x: 6; y: 7; width: 5; height: 5; radius: 2.5; color: Theme.accent }
            Text {
                id: pText
                x: blk.kind === "li" ? 22 : 0; width: parent.width - x
                wrapMode: Text.WordWrap; textFormat: Text.RichText; lineHeight: 1.25
                text: root.rich(blk.text); color: blk.kind === "li" ? Theme.text : Theme.muted; font.pixelSize: 13
                onLinkActivated: link => Qt.openUrlExternally(link)
            }
        }
    }
    Component {
        id: heading
        Text { text: blk.text; color: Theme.text; font.pixelSize: 15; font.bold: true; topPadding: 6 }
    }
    Component {
        id: codeBlock
        Item { height: cb.height + 4; CodeBox { id: cb; x: 22; width: parent.width - 22; lines: blk.text.split("\n") } }
    }

    GrubConfirm { id: grubDialog }
}
