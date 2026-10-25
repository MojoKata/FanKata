import QtQuick
import "."

// Probe-pill thermometer (requirement 5.3.1.1): four 25 °C steps up to 100 °C.
// ≤25 °C shows only the bulb, in blue; then yellow (⅓ of the stem), orange (⅔), red (full).
// Whole-pixel geometry, all centred on x = 8, so the column always sits in the middle
// of the tube (fractional positions snap to different pixels and drift off-centre).
Item {
    id: root
    property var value: null
    readonly property bool known: value !== null && value !== undefined
    readonly property int step: known ? Theme.tempStep(value) : 0
    readonly property color color: known ? Theme.tempColor(value) : Theme.faint
    width: 16; height: 20
    // tube: x 5..11 (1 px wall), y 0..15
    Rectangle {
        x: 5; y: 0; width: 6; height: 15; radius: 3
        color: "transparent"; border.color: root.color; border.width: 1
    }
    // column: x 7..9 (a 1 px gap to each wall). The visible stem above the bulb is
    // 10 px (y 2..12), so the steps show as 3, 7 and 10 px.
    Rectangle {
        readonly property int fill: Math.round(10 * root.step / 3)
        visible: fill > 0
        x: 7; width: 2; radius: 1
        y: 12 - fill
        height: fill + 3                                     // runs into the bulb
        color: root.color
    }
    // bulb: x 4..12, y 12..20, centred on 8
    Rectangle {
        x: 4; y: 12; width: 8; height: 8; radius: 4
        color: root.color
    }
}
