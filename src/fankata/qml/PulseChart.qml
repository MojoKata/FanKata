import QtQuick
import "."

// Commanded duty (dashed square wave) vs. measured RPM during a Speed pulse.
Canvas {
    id: root
    property var pulse: null        // {elapsed, length, low, samples: [[t, duty, rpm]]}
    property bool finished: false
    onPulseChanged: requestPaint()
    onWidthChanged: requestPaint()
    Connections { target: Theme; function onDarkChanged() { root.requestPaint() } }
    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        if (!pulse) return
        const L = 40, T = 8, pw = width - L - 8, ph = height - T - 24
        const len = pulse.length || 8
        const rpms = (pulse.samples || []).map(s => s[2]).filter(v => v !== null && v !== undefined)
        const top = Math.max(1000, Math.ceil(Math.max.apply(null, rpms.concat([0])) * 1.1 / 500) * 500)
        const X = t => L + t / len * pw, Yr = r => T + ph - r / top * ph, Yd = d => T + ph - d / 100 * ph
        ctx.font = "10.5px sans-serif"; ctx.lineWidth = 1
        for (let r = 0; r <= top; r += top > 2500 ? 1000 : 500) {
            ctx.strokeStyle = Theme.grid; ctx.beginPath(); ctx.moveTo(L, Math.round(Yr(r)) + 0.5); ctx.lineTo(L + pw, Math.round(Yr(r)) + 0.5); ctx.stroke()
            ctx.fillStyle = Theme.faint; ctx.textAlign = "right"; ctx.fillText(r ? (r / 1000) + "k" : "0", L - 8, Yr(r) + 4)
        }
        ctx.textAlign = "center"
        for (let t = 0; t <= len; t += 2) ctx.fillText(t + " s", X(t), T + ph + 18)
        // commanded duty
        ctx.save()
        if (ctx.setLineDash) ctx.setLineDash([4, 3])
        ctx.strokeStyle = Theme.alpha(Theme.muted, 0.7); ctx.lineWidth = 1.5
        ctx.beginPath()
        for (let t = 0; t < len; t++) {
            const d = t % 2 === 0 ? 100 : pulse.low
            if (t === 0) ctx.moveTo(X(0), Yd(d)); else ctx.lineTo(X(t), Yd(d))
            ctx.lineTo(X(t + 1), Yd(d))
        }
        ctx.stroke()
        ctx.restore()
        const now = Math.min(len, pulse.elapsed || 0)
        if (!finished) { ctx.fillStyle = Theme.alpha(Theme.input, 0.55); ctx.fillRect(X(now), T, X(len) - X(now), ph) }
        // measured rpm
        const pts = (pulse.samples || []).filter(s => s[2] !== null && s[2] !== undefined)
        if (pts.length > 1) {
            ctx.beginPath()
            pts.forEach((s, i) => i ? ctx.lineTo(X(s[0]), Yr(s[2])) : ctx.moveTo(X(s[0]), Yr(s[2])))
            ctx.save()
            ctx.lineTo(X(pts[pts.length - 1][0]), T + ph); ctx.lineTo(X(pts[0][0]), T + ph); ctx.closePath()
            const g = ctx.createLinearGradient(0, T, 0, T + ph)
            g.addColorStop(0, Theme.alpha(Theme.accent, 0.3)); g.addColorStop(1, Theme.alpha(Theme.accent, 0))
            ctx.fillStyle = g; ctx.fill()
            ctx.restore()
            ctx.beginPath()
            pts.forEach((s, i) => i ? ctx.lineTo(X(s[0]), Yr(s[2])) : ctx.moveTo(X(s[0]), Yr(s[2])))
            ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2.6; ctx.lineJoin = "round"; ctx.stroke()
            const last = pts[pts.length - 1]
            if (!finished) {
                ctx.strokeStyle = Theme.alpha(Theme.text, 0.35); ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(X(now), T - 4); ctx.lineTo(X(now), T + ph); ctx.stroke()
                ctx.fillStyle = Theme.alpha(Theme.accent, 0.25); ctx.beginPath(); ctx.arc(X(last[0]), Yr(last[2]), 9, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = Theme.accent; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                ctx.beginPath(); ctx.arc(X(last[0]), Yr(last[2]), 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            }
        }
    }
}
