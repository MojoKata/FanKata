import QtQuick
import "."

// A Curve graph. The line is drawn from backend.curveSamples(), the same PCHIP
// evaluation the service uses to set fan speeds (requirement 6.5.1).
// Interactive mode: click a dot to remove it, click empty space to add one (6.7).
Item {
    id: root
    property var points: []
    property bool allowZero: false
    property bool labels: true
    property bool markers: true
    property bool interactive: false
    property bool fill: true
    property bool showFloor: labels && !allowZero
    property real lineWidth: 3
    property real markerRadius: 5
    property var ops: []                 // live fan markers: [{v, label}]
    property string curveName: ""
    property color background: Theme.surface
    property bool opsLabels: true
    signal message(string text)

    readonly property real padL: labels ? 44 : 3
    readonly property real padB: labels ? 30 : 3
    readonly property real padR: labels ? 26 : 3
    readonly property real padT: labels ? 14 : 3
    readonly property real pw: Math.max(1, width - padL - padR)
    readonly property real ph: Math.max(1, height - padT - padB)
    function sx(v) { return padL + v / 100 * pw }
    function sy(v) { return padT + ph - v / 100 * ph }
    function fromX(px) { return (px - padL) / pw * 100 }
    function fromY(py) { return (padT + ph - py) / ph * 100 }

    readonly property var samples: backend.curveSamples(points || [])
    function yAt(v) {
        const s = samples
        if (!s || !s.length) return 0
        const f = Math.max(0, Math.min(s.length - 1, v * 2)), i = Math.floor(f), j = Math.min(s.length - 1, i + 1)
        return s[i] + (s[j] - s[i]) * (f - i)
    }

    // hover state: "" | "add" | "invalid" | "remove"
    property string hoverKind: ""
    property int hoverIndex: -1
    property real hx: 0
    property real hy: 0
    property string hoverReason: ""
    property var band: [0, 100]

    function setHover(kind, a, b) {        // also used by the screenshot tour
        if (kind === "remove") { hoverKind = "remove"; hoverIndex = a }
        else if (kind === "add" || kind === "invalid") {
            hx = a; hy = b
            hoverReason = backend.addPointReason(curveName, a, b)
            hoverKind = hoverReason ? "invalid" : "add"
            band = backend.validBand(curveName, a)
            hoverIndex = -1
        } else { hoverKind = ""; hoverIndex = -1 }
        canvas.requestPaint()
    }

    function updateHover(px, py) {
        if (px < padL - 6 || px > padL + pw + 6 || py < padT - 6 || py > padT + ph + 6) { setHover(""); return }
        for (let i = 0; i < points.length; i++) {
            const dx = sx(points[i][0]) - px, dy = sy(points[i][1]) - py
            if (dx * dx + dy * dy <= 121) { setHover("remove", i); return }
        }
        const x = Math.max(0, Math.min(100, Math.round(fromX(px))))
        const y = Math.max(0, Math.min(100, Math.round(fromY(py))))
        setHover("add", x, y)
    }

    function act() {
        let err = ""
        if (hoverKind === "remove") {
            err = points.length <= 2 ? "A curve needs at least two points." : backend.removePoint(curveName, hoverIndex)
            if (!err) setHover("")
        } else if (hoverKind === "add") {
            err = backend.addPoint(curveName, hx, hy)
            if (!err) { hoverKind = "remove"; hoverIndex = -1 }
        } else if (hoverKind === "invalid") {
            err = hoverReason
        }
        if (err) root.message(err)
    }

    onPointsChanged: canvas.requestPaint()
    onSamplesChanged: canvas.requestPaint()
    onOpsChanged: canvas.requestPaint()
    onAllowZeroChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    Connections { target: Theme; function onDarkChanged() { canvas.requestPaint() } }

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: root.draw(getContext("2d"))
    }

    function dashed(ctx, on) { if (ctx.setLineDash) ctx.setLineDash(on ? [4, 4] : []) }

    function draw(ctx) {
        ctx.reset()
        const L = padL, T = padT
        if (labels) {
            ctx.lineWidth = 1
            for (let v = 0; v <= 100; v += 20) {
                ctx.strokeStyle = Theme.grid
                ctx.beginPath(); ctx.moveTo(L, Math.round(sy(v)) + 0.5); ctx.lineTo(L + pw, Math.round(sy(v)) + 0.5); ctx.stroke()
            }
            for (let v = 0; v <= 100; v += 10) {
                ctx.strokeStyle = v % 20 ? Theme.alpha(Theme.grid, 0.5) : Theme.grid
                ctx.beginPath(); ctx.moveTo(Math.round(sx(v)) + 0.5, T); ctx.lineTo(Math.round(sx(v)) + 0.5, T + ph); ctx.stroke()
            }
            ctx.fillStyle = Theme.faint
            ctx.font = "11px sans-serif"
            ctx.textAlign = "right"
            for (let v = 0; v <= 100; v += 20) ctx.fillText(v + "%", L - 10, sy(v) + 4)
            ctx.textAlign = "center"
            for (let v = 0; v <= 100; v += 10) ctx.fillText(v === 100 ? "100 °C" : v + "°", sx(v), T + ph + 20)
        }
        const s = samples
        if (!s || s.length < 2) return
        const g = ctx.createLinearGradient(sx(0), 0, sx(100), 0)
        for (const st of Theme.heatStops) g.addColorStop(st[0], st[1])
        const path = () => {
            ctx.beginPath()
            for (let i = 0; i < s.length; i++) i ? ctx.lineTo(sx(i * 0.5), sy(s[i])) : ctx.moveTo(sx(0), sy(s[0]))
        }
        if (fill) {
            ctx.save()
            path(); ctx.lineTo(sx(100), sy(0)); ctx.lineTo(sx(0), sy(0)); ctx.closePath()
            ctx.clip()
            ctx.globalAlpha = Theme.dark ? 0.34 : 0.28
            ctx.fillStyle = g
            ctx.fillRect(L, T, pw, ph)
            ctx.globalAlpha = 1
            const fade = ctx.createLinearGradient(0, T, 0, T + ph)
            fade.addColorStop(0, Theme.alpha(background, 0))
            fade.addColorStop(1, Theme.alpha(background, 0.92))
            ctx.fillStyle = fade
            ctx.fillRect(L, T, pw, ph)
            ctx.restore()
        }
        if (showFloor) {
            const y20 = sy(20)
            ctx.save()
            ctx.beginPath(); ctx.rect(L, y20, pw, sy(0) - y20); ctx.clip()
            ctx.strokeStyle = Theme.alpha(Theme.faint, Theme.dark ? 0.22 : 0.2)
            ctx.lineWidth = 2.2
            for (let x = L - ph; x < L + pw + ph; x += 7) { ctx.beginPath(); ctx.moveTo(x, sy(0)); ctx.lineTo(x + (sy(0) - y20), y20); ctx.stroke() }
            ctx.restore()
            ctx.save()
            if (ctx.setLineDash) ctx.setLineDash([5, 4])
            ctx.strokeStyle = Theme.faint; ctx.lineWidth = 1.2
            ctx.beginPath(); ctx.moveTo(L, y20); ctx.lineTo(L + pw, y20); ctx.stroke()
            ctx.restore()
            ctx.fillStyle = Theme.faint; ctx.font = "bold 11.5px sans-serif"; ctx.textAlign = "right"
            ctx.fillText("Minimum 20 %", L + pw - 10, sy(10) + 4.5)
        }
        path()
        ctx.strokeStyle = g; ctx.lineWidth = lineWidth; ctx.lineJoin = "round"; ctx.lineCap = "round"
        ctx.stroke()

        for (const op of ops || []) {
            if (op.v === null || op.v === undefined) continue
            const v = Math.max(0, Math.min(100, op.v)), ox = sx(v), oy = sy(yAt(v)), c = Theme.heat(v)
            ctx.save()
            if (ctx.setLineDash) ctx.setLineDash([4, 4])
            ctx.strokeStyle = Theme.alpha(c, 0.8); ctx.lineWidth = 1.4
            ctx.beginPath(); ctx.moveTo(ox, T + ph); ctx.lineTo(ox, oy); ctx.lineTo(L, oy); ctx.stroke()
            ctx.restore()
            ctx.fillStyle = Theme.alpha(c, 0.16); ctx.beginPath(); ctx.arc(ox, oy, 13, 0, Math.PI * 2); ctx.fill()
            ctx.fillStyle = c; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 3
            ctx.beginPath(); ctx.arc(ox, oy, 6.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
        }

        if (hoverKind === "add") {
            ctx.save()
            ctx.strokeStyle = Theme.alpha(Theme.accent, 0.22); ctx.lineWidth = 10; ctx.lineCap = "round"
            ctx.beginPath(); ctx.moveTo(sx(hx), sy(band[0])); ctx.lineTo(sx(hx), sy(band[1])); ctx.stroke()
            ctx.restore()
        }
        if (hoverKind === "add" || hoverKind === "invalid") {
            const c = hoverKind === "add" ? Theme.accent : Theme.err
            ctx.save()
            if (ctx.setLineDash) ctx.setLineDash([3, 4])
            ctx.strokeStyle = Theme.alpha(c, 0.7); ctx.lineWidth = 1.2
            ctx.beginPath(); ctx.moveTo(sx(hx), T + ph); ctx.lineTo(sx(hx), sy(hy)); ctx.lineTo(L, sy(hy)); ctx.stroke()
            if (ctx.setLineDash) ctx.setLineDash([3, 2.5])
            ctx.fillStyle = Theme.surface; ctx.strokeStyle = c; ctx.lineWidth = 2
            ctx.beginPath(); ctx.arc(sx(hx), sy(hy), markerRadius + 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            ctx.restore()
            ctx.strokeStyle = c; ctx.lineWidth = 2.2; ctx.lineCap = "round"
            ctx.beginPath()
            if (hoverKind === "add") {
                ctx.moveTo(sx(hx) - 4, sy(hy)); ctx.lineTo(sx(hx) + 4, sy(hy)); ctx.moveTo(sx(hx), sy(hy) - 4); ctx.lineTo(sx(hx), sy(hy) + 4)
            } else {
                ctx.moveTo(sx(hx) - 3.5, sy(hy) - 3.5); ctx.lineTo(sx(hx) + 3.5, sy(hy) + 3.5); ctx.moveTo(sx(hx) + 3.5, sy(hy) - 3.5); ctx.lineTo(sx(hx) - 3.5, sy(hy) + 3.5)
            }
            ctx.stroke()
        }

        if (!markers) return
        for (let i = 0; i < points.length; i++) {
            const px = sx(points[i][0]), py = sy(points[i][1]), c = Theme.heat(points[i][0])
            if (hoverKind === "remove" && i === hoverIndex) {
                ctx.fillStyle = Theme.alpha(Theme.err, 0.16); ctx.beginPath(); ctx.arc(px, py, markerRadius + 11, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = Theme.err; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 3
                ctx.beginPath(); ctx.arc(px, py, markerRadius + 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
                ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2.2; ctx.lineCap = "round"
                ctx.beginPath(); ctx.moveTo(px - 3.5, py - 3.5); ctx.lineTo(px + 3.5, py + 3.5); ctx.moveTo(px + 3.5, py - 3.5); ctx.lineTo(px - 3.5, py + 3.5); ctx.stroke()
            } else {
                ctx.fillStyle = Theme.surface; ctx.strokeStyle = c; ctx.lineWidth = markerRadius > 3 ? 2.6 : 1.6
                ctx.beginPath(); ctx.arc(px, py, markerRadius, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            }
        }
    }

    // live fan labels
    Repeater {
        model: root.opsLabels && root.labels ? root.ops : []
        Rectangle {
            readonly property real ox: root.sx(Math.max(0, Math.min(100, modelData.v || 0)))
            visible: modelData.v !== null && modelData.v !== undefined
            height: 26; radius: 13
            width: lbl.implicitWidth + 22
            x: Math.max(root.padL + 4, Math.min(root.padL + root.pw - width - 4, ox - width / 2))
            y: root.padT + 2 + index * 34
            color: Theme.surface
            border.color: Theme.heat(modelData.v || 0); border.width: 1.4
            Text { id: lbl; anchors.centerIn: parent; text: modelData.label; color: Theme.text; font.pixelSize: 12; font.bold: true }
        }
    }

    // hover tooltip
    Rectangle {
        id: tip
        visible: root.interactive && root.hoverKind !== "" && (root.hoverKind !== "remove" || root.hoverIndex >= 0)
        readonly property real ax: root.hoverKind === "remove" && root.hoverIndex >= 0 ? root.sx(root.points[root.hoverIndex][0]) : root.sx(root.hx)
        readonly property real ay: root.hoverKind === "remove" && root.hoverIndex >= 0 ? root.sy(root.points[root.hoverIndex][1]) : root.sy(root.hy)
        property string text_: root.hoverKind === "remove" && root.hoverIndex >= 0
               ? "Click to remove  ·  " + root.points[root.hoverIndex][0] + " °C, " + root.points[root.hoverIndex][1] + " %"
               : root.hoverKind === "add" ? "Click to add  ·  " + root.hx + " °C, " + root.hy + " %"
               : root.hoverReason
        width: tipText.implicitWidth + 24; height: 28; radius: 8
        x: Math.max(0, Math.min(root.width - width, ax - width / 2))
        y: ay - 52 < 0 ? ay + 22 : ay - 52
        color: root.hoverKind === "invalid" ? Theme.err : Theme.tipBg
        Text { id: tipText; anchors.centerIn: parent; text: tip.text_; font.pixelSize: 12; font.bold: true; color: root.hoverKind === "invalid" ? "#ffffff" : Theme.tipFg }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.interactive
        hoverEnabled: root.interactive
        cursorShape: root.hoverKind === "invalid" ? Qt.ForbiddenCursor : root.hoverKind !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPositionChanged: mouse => root.updateHover(mouse.x, mouse.y)
        onExited: root.setHover("")
        onClicked: root.act()
    }
}
