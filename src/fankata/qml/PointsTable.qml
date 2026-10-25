import QtQuick
import QtQuick.Controls.Basic
import "."

Column {
    id: root
    property var curve: null
    property int highlight: -1
    property string error: ""
    property int errorIndex: -1
    property string errorTyped: ""
    signal message(string text)
    spacing: 12
    onCurveChanged: if (curve && error && errorIndex >= curve.points.length) clearError()
    function clearError() { error = ""; errorIndex = -1; errorTyped = "" }
    function showError(i, typed, msg) { errorIndex = i; errorTyped = typed; error = msg }   // also used by the tour

    Item {
        width: root.width; height: pointsTitle.height
        Text { id: pointsTitle; text: "Points"; color: Theme.text; font.pixelSize: 15; font.bold: true }
        Text {
            anchors.left: pointsTitle.right; anchors.leftMargin: 14; anchors.right: parent.right
            anchors.baseline: pointsTitle.baseline
            text: "Click a dot to remove it, click empty space on the graph to add one, or type values below."
            color: Theme.muted; font.pixelSize: 13; elide: Text.ElideRight
        }
    }
    Rectangle {
        width: root.width; height: 104; radius: 14
        color: Theme.surface; border.color: Theme.border
        readonly property int n: root.curve ? root.curve.points.length : 0
        readonly property real colW: (width - 76 - 8) / Math.max(1, n)
        Text { x: 16; y: 25; text: "Temp"; color: Theme.muted; font.pixelSize: 13; font.bold: true }
        Text { x: 16; y: 67; text: "Speed"; color: Theme.muted; font.pixelSize: 13; font.bold: true }
        Repeater {
            model: root.curve ? root.curve.points : []
            Item {
                id: col
                readonly property int i: index
                readonly property bool bad: root.errorIndex === index && root.error !== ""
                x: 76 + index * parent.colW; width: parent.colW; height: parent.height
                Rectangle { visible: root.highlight === col.i; x: 3; y: 4; width: parent.width - 6; height: 96; radius: 10; color: Theme.errSoft }
                Rectangle {
                    x: 6; y: 14; width: parent.width - 12; height: 36; radius: 9; color: Theme.input
                    border.color: tx.activeFocus ? Theme.accent : Theme.border; border.width: tx.activeFocus ? 2 : 1
                    Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: Theme.heat(modelData[0]) }
                    TextField {
                        id: tx
                        anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 4
                        leftPadding: 0; rightPadding: 6
                        horizontalAlignment: TextInput.AlignRight
                        text: modelData[0] + " °C"
                        color: Theme.text; font.pixelSize: 14; font.bold: true
                        background: null
                        onActiveFocusChanged: if (activeFocus) { text = String(modelData[0]); selectAll() } else text = modelData[0] + " °C"
                        onAccepted: root.commit(col.i, text, String(modelData[1]), false)
                    }
                }
                Rectangle {
                    x: 6; y: 56; width: parent.width - 12; height: 36; radius: 9
                    color: col.bad ? Theme.errSoft : Theme.input
                    border.color: col.bad ? Theme.err : ty.activeFocus ? Theme.accent : Theme.border
                    border.width: col.bad || ty.activeFocus ? 2 : 1
                    Icon { visible: col.bad; x: 9; anchors.verticalCenter: parent.verticalCenter; name: "warn"; size: 15; color: Theme.err }
                    TextField {
                        id: ty
                        anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 4
                        leftPadding: 0; rightPadding: 6
                        horizontalAlignment: TextInput.AlignRight
                        text: col.bad ? root.errorTyped + " %" : modelData[1] + " %"
                        color: col.bad ? Theme.err : Theme.text; font.pixelSize: 14; font.bold: true
                        background: null
                        onActiveFocusChanged: if (activeFocus) { text = col.bad ? root.errorTyped : String(modelData[1]); selectAll() }
                                              else if (!col.bad) text = modelData[1] + " %"
                        onAccepted: root.commit(col.i, String(modelData[0]), text, true)
                        Keys.onEscapePressed: { root.clearError(); focus = false }
                    }
                }
            }
        }
    }
    function commit(i, xs, ys, speed) {
        const err = backend.setPoint(curve.name, i, xs, ys)
        if (err) showError(i, speed ? ys.replace("%", "").trim() : String(curve.points[i][1]), err)
        else clearError()
    }
    Rectangle {
        visible: root.error !== ""
        width: root.width; height: 38; radius: 10; color: Theme.errSoft
        Icon { x: 14; anchors.verticalCenter: parent.verticalCenter; name: "warn"; color: Theme.err }
        Text { x: 40; anchors.verticalCenter: parent.verticalCenter; text: root.error; color: Theme.err; font.pixelSize: 13; font.bold: true; width: parent.width - 150; elide: Text.ElideRight }
        Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; text: "Not applied"; color: Theme.err; opacity: 0.8; font.pixelSize: 12 }
    }
}
