import QtQuick
import QtQuick.Controls.Basic
import "."

Popup {
    id: root
    property string original: ""      // "" for a new probe
    property var check: ({})
    property string saveError: ""
    signal message(string text)
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: 560
    padding: 30
    closePolicy: Popup.CloseOnEscape
    Overlay.modal: Rectangle { color: Theme.scrim }
    background: Rectangle {
        radius: 20; color: Theme.surface; border.color: Theme.border
        Rectangle { z: -1; anchors.fill: parent; anchors.topMargin: 8; anchors.bottomMargin: -8; radius: 20; color: "#000000"; opacity: Theme.dark ? 0.4 : 0.12 }
    }

    function openFor(name) {
        original = name || ""
        const p = backend.probes.find(q => q.name === name)
        nameField.text = p ? p.name : ""
        exprField.text = p ? p.expr : ""
        saveError = ""
        refresh()
        open()
        nameField.forceActiveFocus()
    }
    function refresh() { check = backend.checkProbe(original, nameField.text, exprField.text); history.values = backend.expressionHistory(exprField.text) }
    function insert(s) {
        const t = exprField.text, c = exprField.cursorPosition
        const pre = t.slice(0, c), post = t.slice(c)
        const pad = s.length > 1 ? " " : ""
        const ins = (pre && !pre.endsWith(" ") && pad ? " " : "") + s + (pad && !post.startsWith(" ") ? " " : "")
        exprField.text = pre + ins + post
        exprField.cursorPosition = (pre + ins).length
        exprField.forceActiveFocus()
    }
    function applySuggestion() {
        const t = exprField.text
        exprField.text = t.slice(0, check.pos) + check.suggestion + t.slice(check.pos + check.length)
    }
    Timer { interval: 1000; repeat: true; running: root.visible; onTriggered: root.refresh() }

    readonly property bool exprError: exprField.text.length > 0 && !check.exprOk
    readonly property bool canSave: !!check.nameOk && !!check.exprOk && backend.connected

    contentItem: Column {
        spacing: 0
        Item {
            width: parent.width; height: 34
            Text { text: root.original ? "Edit probe" : "New custom probe"; color: Theme.text; font.pixelSize: 21; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
            IconButton { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; round: true; icon: "x"; onClicked: root.close() }
        }
        Item { width: 1; height: 16 }
        Text { text: "Name"; color: Theme.muted; font.pixelSize: 13; font.bold: true }
        Item { width: 1; height: 8 }
        TextField {
            id: nameField
            width: parent.width; height: 42
            font.pixelSize: 15; font.family: Theme.mono
            color: Theme.text; leftPadding: 14
            placeholderText: "e.g. blend"; placeholderTextColor: Theme.faint
            background: Rectangle { radius: 11; color: Theme.input; border.color: nameField.activeFocus ? Theme.accent : Theme.border; border.width: nameField.activeFocus ? 2 : 1 }
            onTextChanged: root.refresh()
            Rectangle {
                visible: nameField.text.length > 0
                anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                width: 18; height: 18; radius: 9; color: root.check.nameOk ? Theme.okSoft : Theme.errSoft
                Icon { anchors.centerIn: parent; name: root.check.nameOk ? "check" : "x"; size: 12; lineWidth: 2; color: root.check.nameOk ? Theme.ok : Theme.err }
            }
        }
        Item { width: 1; height: 8 }
        Text {
            text: root.check.nameError && nameField.text.length ? root.check.nameError : "Starts with a letter, then letters, digits and _ only. Unique among custom probes."
            color: root.check.nameError && nameField.text.length ? Theme.err : Theme.muted; font.pixelSize: 12
        }
        Item { width: 1; height: 20 }
        Text { text: "Expression"; color: Theme.muted; font.pixelSize: 13; font.bold: true }
        Item { width: 1; height: 8 }
        Rectangle {
            width: parent.width; height: 56; radius: 11; color: Theme.input
            border.width: 2
            border.color: root.exprError ? Theme.err : exprField.activeFocus ? Theme.accent : Theme.border
            FontMetrics { id: fm; font.family: Theme.mono; font.pixelSize: 15 }
            // colour-coded tokens drawn under a transparent text field
            Item {
                x: 16; y: 0; height: parent.height; width: parent.width - 32
                clip: true
                Repeater {
                    model: root.check.tokens || []
                    Item {
                        x: modelData.pos * fm.averageCharacterWidth - exprField.scroll
                        width: modelData.text.length * fm.averageCharacterWidth
                        height: parent.height
                        readonly property bool isError: root.exprError && modelData.pos >= root.check.pos && modelData.pos < root.check.pos + root.check.length
                        Rectangle {
                            visible: modelData.kind === "probe" && !parent.isError
                            anchors.verticalCenter: parent.verticalCenter
                            x: -4; width: parent.width + 8; height: 24; radius: 6; color: Theme.accentSoft
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.text
                            font.family: Theme.mono; font.pixelSize: 15
                            font.bold: modelData.kind === "probe" || parent.isError
                            color: parent.isError ? Theme.err : modelData.kind === "probe" ? Theme.accent
                                 : modelData.kind === "number" ? (Theme.dark ? "#fdba74" : "#c2410c")
                                 : modelData.kind === "op" ? Theme.muted : Theme.text
                        }
                        Canvas {     // wavy underline under the error
                            visible: parent.isError
                            y: parent.height / 2 + 10; width: parent.width; height: 5
                            onPaint: { const c = getContext("2d"); c.reset(); c.strokeStyle = Theme.err; c.lineWidth = 1.4; c.beginPath()
                                       for (let x = 0; x <= width; x += 2) (x ? c.lineTo(x, (x / 2) % 2 ? 1 : 4) : c.moveTo(0, 4)); c.stroke() }
                        }
                    }
                }
            }
            TextField {
                id: exprField
                readonly property real scroll: Math.max(0, cursorRectangle.x - (width - leftPadding - rightPadding - 8))
                anchors.fill: parent
                leftPadding: 16; rightPadding: 16
                font.family: Theme.mono; font.pixelSize: 15
                color: "transparent"
                selectedTextColor: "transparent"
                selectionColor: Theme.alpha(Theme.accent, 0.3)
                placeholderText: "e.g. sys.cpu * .9 + sys.gpu / 10"; placeholderTextColor: Theme.faint
                background: null
                cursorDelegate: Rectangle { width: 1.6; color: Theme.text; visible: exprField.cursorVisible }
                onTextChanged: root.refresh()
            }
        }
        Item { width: 1; height: root.exprError ? 12 : 0 }
        Row {
            visible: root.exprError
            spacing: 8
            height: 24
            Icon { name: "warn"; size: 15; color: Theme.err; anchors.verticalCenter: parent.verticalCenter }
            Text { text: root.check.error + (root.check.suggestion ? " Did you mean" : ""); color: Theme.err; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
            Pill {
                visible: !!root.check.suggestion
                text: root.check.suggestion || ""; mono: true; fg: Theme.accent; color: Theme.accentSoft; height: 22
                anchors.verticalCenter: parent.verticalCenter
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.applySuggestion() }
            }
            Text { visible: !!root.check.suggestion; text: "?"; color: Theme.err; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
        }
        Item { width: 1; height: 16 }
        Row {
            spacing: 6
            Text { text: "Insert"; color: Theme.faint; font.pixelSize: 12; font.bold: true; width: 44; anchors.verticalCenter: parent.verticalCenter }
            Repeater {
                model: {
                    const names = backend.probes.filter(p => p.name !== root.original && (p.kind === "custom"
                                    || ["sys.cpu", "sys.gpu", "sys.nvme", "sys.coolant"].indexOf(p.name) >= 0)).map(p => p.name)
                    return names.slice(0, 6)
                }
                Pill {
                    text: modelData; mono: true; bold: false; fg: Theme.accent; color: Theme.surface; border.color: Theme.border; border.width: 1; size: 12
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.insert(modelData) }
                }
            }
        }
        Item { width: 1; height: 8 }
        Row {
            spacing: 6
            Item { width: 44; height: 1 }
            Repeater {
                model: ["+", "-", "*", "/", "^", "(", ")"]
                Rectangle {
                    width: 30; height: 26; radius: 7; color: opArea.containsMouse ? Theme.hover : Theme.input; border.color: Theme.border
                    Text { anchors.centerIn: parent; text: modelData; font.family: Theme.mono; font.pixelSize: 14; font.bold: true; color: Theme.text }
                    MouseArea { id: opArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.insert(modelData) }
                }
            }
            Text { text: "   precedence: ^  then * /  then + -"; color: Theme.faint; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
        }
        Item { width: 1; height: 18 }
        Rectangle {
            width: parent.width; height: 76; radius: 14
            readonly property bool has: !!root.check.exprOk && root.check.value !== null && root.check.value !== undefined
            color: has ? Theme.illusA : Theme.input
            border.width: has ? 0 : 1; border.color: Theme.border
            Text { x: 18; y: 14; text: "Current value"; color: Theme.muted; font.pixelSize: 12; font.bold: true }
            Row {
                x: 18; y: 34; spacing: 14
                Text {
                    text: parent.parent.has ? Theme.fmt1(root.check.value) + " °C" : "—"
                    color: parent.parent.has ? Theme.heat(root.check.value) : Theme.faint
                    font.pixelSize: 28; font.bold: true
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.parent.has ? root.check.formula : (root.check.exprOk && root.check.error ? root.check.error : "Fix the expression to see a live value")
                    color: parent.parent.has ? Theme.muted : Theme.faint
                    font.pixelSize: 12; font.family: parent.parent.has ? Theme.mono : Qt.application.font.family
                    width: 250; elide: Text.ElideRight
                }
            }
            Sparkline {
                id: history
                visible: parent.has
                anchors.right: parent.right; anchors.rightMargin: 18; y: 18
                width: 132; height: 40; lineWidth: 2; area: true
                color: parent.has ? Theme.heat(root.check.value) : Theme.faint
            }
        }
        Item { width: 1; height: root.saveError ? 10 : 0 }
        Text { visible: root.saveError !== ""; text: root.saveError; color: Theme.err; font.pixelSize: 13; font.bold: true; width: parent.width; wrapMode: Text.WordWrap }
        Item { width: 1; height: 20 }
        Item {
            width: parent.width; height: 38
            FButton {
                visible: root.original !== ""
                implicitHeight: 38
                text: "Delete"; icon: "trash"; danger: true
                enabledButton: backend.connected
                onClicked: { const e = backend.deleteProbe(root.original); if (e) root.saveError = e; else root.close() }
            }
            Row {
                anchors.right: parent.right; spacing: 10
                FButton { implicitHeight: 38; text: "Cancel"; onClicked: root.close() }
                FButton {
                    implicitHeight: 38
                    text: root.original ? "Save" : "Create probe"
                    primary: true; enabledButton: root.canSave
                    onClicked: {
                        const e = backend.saveProbe(root.original, nameField.text, exprField.text)
                        if (e) root.saveError = e; else root.close()
                    }
                }
            }
        }
    }
    function setDemo(name, expr) { nameField.text = name; exprField.text = expr; exprField.cursorPosition = expr.length; refresh() }
}
