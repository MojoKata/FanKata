import QtQuick
import "."

// Recent probe readings, one sample per second. The x axis is a fixed window
// (`window` samples), newest at the right, so a short history fills in from the
// right instead of being stretched. null values (no reading) leave a gap.
Canvas {
    id: root
    property var values: []
    property int window: 60
    property color color: Theme.accent
    property real lineWidth: 1.4
    property bool area: false
    onValuesChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const all = values || []
        const v = all.slice(-window)
        const nums = v.filter(x => x !== null && x !== undefined)
        if (nums.length < 1) return
        let mn = Math.min.apply(null, nums), mx = Math.max.apply(null, nums)
        if (mx - mn < 1) { const c = (mx + mn) / 2; mn = c - 0.5; mx = c + 0.5 }   // don't magnify noise
        const pad = lineWidth + 1.5
        const step = (width - 2 * pad) / Math.max(1, window - 1)
        const X = i => width - pad - (v.length - 1 - i) * step
        const Y = y => pad + (height - 2 * pad) * (1 - (y - mn) / (mx - mn))
        // one path per run of readings (gaps where a reading was missing)
        const runs = []
        let cur = []
        for (let i = 0; i < v.length; i++) {
            if (v[i] === null || v[i] === undefined) { if (cur.length) runs.push(cur); cur = [] }
            else cur.push(i)
        }
        if (cur.length) runs.push(cur)
        for (const run of runs) {
            if (area && run.length > 1) {
                ctx.beginPath()
                run.forEach((i, k) => k ? ctx.lineTo(X(i), Y(v[i])) : ctx.moveTo(X(i), Y(v[i])))
                ctx.lineTo(X(run[run.length - 1]), height); ctx.lineTo(X(run[0]), height); ctx.closePath()
                const g = ctx.createLinearGradient(0, 0, 0, height)
                g.addColorStop(0, Theme.alpha(color, 0.28)); g.addColorStop(1, Theme.alpha(color, 0))
                ctx.fillStyle = g; ctx.fill()
            }
            ctx.beginPath()
            run.forEach((i, k) => k ? ctx.lineTo(X(i), Y(v[i])) : ctx.moveTo(X(i), Y(v[i])))
            ctx.strokeStyle = color; ctx.lineWidth = lineWidth; ctx.lineJoin = "round"; ctx.lineCap = "round"
            ctx.stroke()
        }
        const last = v.length - 1
        if (v[last] !== null && v[last] !== undefined) {
            ctx.fillStyle = color
            ctx.beginPath(); ctx.arc(X(last), Y(v[last]), lineWidth + 1, 0, Math.PI * 2); ctx.fill()
        }
    }
}
