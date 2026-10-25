import QtQuick
import QtQuick.Controls.Basic
import "."
import "Markdown.js" as Md

// Add (or remove) the acpi_enforce_resources=lax boot option (requirement 4.7.3):
// shows the file and the kernel boot options before and after, then writes them.
Popup {
    id: root
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    readonly property var win: ApplicationWindow.window
    width: Math.min(760, (win && win.width > 0 ? win.width : 1280) - 60)
    padding: 30
    closePolicy: Popup.CloseOnEscape
    Overlay.modal: Rectangle { color: Theme.scrim }
    background: Rectangle {
        radius: 20; color: Theme.surface; border.color: Theme.border
        Rectangle { z: -1; anchors.fill: parent; anchors.topMargin: 8; anchors.bottomMargin: -8; radius: 20; color: "#000000"; opacity: Theme.dark ? 0.4 : 0.12 }
    }
    property var p: ({})
    readonly property bool remove: !!p.remove
    function openFor(preview) { p = preview; open() }
    function rich(s) { return Md.inline(s || "", { mono: Theme.mono, codeBg: Theme.track, code: Theme.text, link: Theme.accent }) }
    function esc(s) { return Md.esc(s) }
    // the boot options with the added (or removed) word highlighted
    function options(line, mark, fg, bg) {
        return line.split(" ").filter(w => w).map(w => w === mark
            ? "<span style=\"background-color:" + bg + "; color:" + fg + "\"><b>&nbsp;" + esc(w) + "&nbsp;</b></span>" : esc(w)).join(" ") || "<i>(none)</i>"
    }

    contentItem: Column {
        spacing: 14
        Item {
            width: parent.width; height: 30
            Text { text: root.remove ? "Remove the boot option?" : "Add a boot option?"; color: Theme.text; font.pixelSize: 21; font.bold: true }
            IconButton { anchors.right: parent.right; round: true; icon: "x"; onClicked: root.close() }
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap; textFormat: Text.RichText; color: Theme.muted; font.pixelSize: 13
            text: root.rich(root.remove ? "Fankata will delete one file, then run `update-grub`. It takes effect when you restart."
                                        : "Fankata will write one new file, then run `update-grub`. Nothing else changes. It takes effect when you restart.")
        }
        BeforeAfter {
            width: parent.width; title: root.p.file || ""; mono: true
            note: root.p.before === null || root.p.before === undefined ? "new file" : root.remove ? "deleted" : "replaced"
            before: root.p.before === null || root.p.before === undefined ? "<i>(no file)</i>"
                    : root.p.before.map(l => root.esc(l)).join("<br>")
            beforeTint: root.remove ? Theme.errSoft : "transparent"
            after: root.p.after ? root.p.after.map(l => root.esc(l)).join("<br>") : "<i>(no file)</i>"
            afterTint: root.p.after ? Theme.okSoft : "transparent"
        }
        BeforeAfter {
            width: parent.width; title: "Kernel boot options"; note: "from /etc/default/grub and grub.d"
            before: root.options(root.p.cmd_before || "", root.remove ? "acpi_enforce_resources=lax" : "", Theme.err, Theme.errSoft)
            after: root.options(root.p.cmd_after || "", "acpi_enforce_resources=lax", Theme.ok, Theme.okSoft)
        }
        Rectangle {
            visible: !root.remove
            width: parent.width; height: warnText.height + 26; radius: 12; color: Theme.warnSoft
            Icon { x: 14; y: 13; name: "warn"; color: Theme.warn }
            Text {
                id: warnText
                x: 40; y: 13; width: parent.width - 56; wrapMode: Text.WordWrap; textFormat: Text.RichText
                color: Theme.text; font.pixelSize: 13; lineHeight: 1.2
                text: root.rich("`acpi_enforce_resources=lax` lets any driver use hardware the firmware reserved. It’s the usual fix for fan chips, "
                                + "but on a few boards it causes other conflicts. To undo it, use **Remove boot option** in Troubleshoot fans.")
            }
        }
        Item {
            width: parent.width; height: 46
            Rectangle { x: -30; width: parent.width + 60; height: 1; color: Theme.border }
            FButton {
                y: 8; implicitHeight: 38; icon: "copy"; text: "Copy commands instead"
                onClicked: { troubleshoot.copyText(troubleshoot.grubCommands(root.remove)); backend.toast("info", "Commands copied."); root.close() }
            }
            Row {
                anchors.right: parent.right; y: 8; spacing: 10
                FButton { implicitHeight: 38; text: "Cancel"; onClicked: root.close() }
                FButton {
                    implicitHeight: 38; primary: true; icon: "lock"
                    text: root.remove ? "Remove and update GRUB" : "Write and update GRUB"
                    onClicked: { troubleshoot.applyGrub(root.remove); root.close() }
                }
            }
        }
    }

    component BeforeAfter: Rectangle {
        property string title
        property string note
        property bool mono: false
        property string before
        property string after
        property color beforeTint: "transparent"
        property color afterTint: "transparent"
        height: inner.height + 2
        radius: 12; color: Theme.input; border.color: Theme.border
        Column {
            id: inner
            y: 1; width: parent.width
            Item {
                width: parent.width; height: 40
                Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: title; color: Theme.text; font.pixelSize: 13; font.bold: true; font.family: mono ? Theme.mono : Qt.application.font.family }
                Text { anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: note; color: Theme.muted; font.pixelSize: 12 }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
            }
            Repeater {
                model: [["BEFORE", before, beforeTint], ["AFTER", after, afterTint]]
                Item {
                    width: inner.width; height: lab.height + block.height + 26
                    Text { id: lab; x: 16; y: 12; text: modelData[0]; color: Theme.faint; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.1 }
                    Rectangle {
                        id: block
                        x: 12; y: lab.y + lab.height + 6; width: parent.width - 24; height: code.height + 10; radius: 6; color: modelData[2]
                        Text {
                            id: code
                            x: 8; y: 5; width: parent.width - 16; wrapMode: Text.WrapAnywhere; textFormat: Text.RichText
                            text: modelData[1]; color: Theme.text; font.family: Theme.mono; font.pixelSize: 12; lineHeight: 1.3
                        }
                    }
                }
            }
        }
    }
}
