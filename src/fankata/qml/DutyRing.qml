import QtQuick
import "."

Item {
    id: root
    property var value: null        // duty %, or null when unknown
    property bool active: false
    property real shown: value === null || value === undefined ? 0 : value
    Behavior on shown { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
    width: 48; height: 48
    onShownChanged: canvas.requestPaint()
    onActiveChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    Connections { target: Theme; function onDarkChanged() { canvas.requestPaint() } }
    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const k = width / 48
            const c = width / 2, r = width / 2 - 4 * k
            ctx.lineWidth = 5 * k
            ctx.strokeStyle = Theme.track
            ctx.beginPath(); ctx.arc(c, c, r, 0, Math.PI * 2); ctx.stroke()
            if (root.value === null || root.value === undefined) return
            // one thin slice per 2°, each coloured by its position on the dial
            const end = Math.min(100, root.shown) / 100 * Math.PI * 2
            if (end <= 0) return
            ctx.globalAlpha = root.active ? 1 : (Theme.dark ? 0.55 : 0.6)
            const step = Math.PI / 90
            for (let a = 0; a < end; a += step) {
                ctx.strokeStyle = Theme.duty((a + step / 2) / (Math.PI * 2))
                ctx.beginPath()
                ctx.arc(c, c, r, -Math.PI / 2 + a, -Math.PI / 2 + Math.min(end, a + step * 1.3))
                ctx.stroke()
            }
            for (const [ang, col] of [[0, Theme.duty(0)], [end, Theme.duty(end / (Math.PI * 2))]]) {
                ctx.fillStyle = col
                ctx.beginPath()
                ctx.arc(c + r * Math.sin(ang), c - r * Math.cos(ang), 2.5 * k, 0, Math.PI * 2)
                ctx.fill()
            }
        }
    }
    Text {
        anchors.centerIn: parent
        text: root.value === null || root.value === undefined ? "—" : Math.round(root.value) + "%"
        color: root.value === null || root.value === undefined ? Theme.faint : Theme.text
        font.pixelSize: Math.round(13 * root.width / 48); font.bold: true
    }
}
