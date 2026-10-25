pragma Singleton
import QtQuick

// Design tokens from the mockups (screenshots/src/render.js THEMES).
QtObject {
    id: t
    property string mode: "system"          // "system" | "dark" | "light"
    readonly property bool dark: mode === "dark"
        || (mode !== "light" && Qt.styleHints.colorScheme !== Qt.ColorScheme.Light)

    readonly property color bg: dark ? "#15171e" : "#f5f6fa"
    readonly property color side: dark ? "#1a1c24" : "#eff1f6"
    readonly property color surface: dark ? "#1f222b" : "#ffffff"
    readonly property color raised: dark ? "#262a35" : "#ffffff"
    readonly property color hover: dark ? "#2f3442" : "#f3f4f8"
    readonly property color border: dark ? "#2c303c" : "#e4e7ef"
    readonly property color borderStrong: dark ? "#3a3f4d" : "#d4d8e3"
    readonly property color text: dark ? "#eceef4" : "#1b1f2b"
    readonly property color muted: dark ? "#9aa0b3" : "#6a7084"
    readonly property color faint: dark ? "#686d80" : "#a0a6b6"
    readonly property color accent: dark ? "#8089ff" : "#5a67f2"
    readonly property color accentSoft: dark ? "#2a2d52" : "#eceefe"
    readonly property color ok: dark ? "#34d399" : "#0f9f6c"
    readonly property color okSoft: dark ? "#133a2d" : "#e2f6ed"
    readonly property color warn: dark ? "#fbbf24" : "#c26a04"
    readonly property color warnSoft: dark ? "#3a2e12" : "#fdf1dc"
    readonly property color err: dark ? "#fb7185" : "#e0445a"
    readonly property color errSoft: dark ? "#3d1a22" : "#fde8eb"
    readonly property color track: dark ? "#2c303c" : "#eceef4"
    readonly property color illusA: dark ? "#222739" : "#edf2ff"
    readonly property color illusB: dark ? "#2a2442" : "#f5eeff"
    readonly property color illusOff: dark ? "#1b1e26" : "#f2f3f7"
    readonly property color grid: dark ? "#2a2e39" : "#edeff4"
    readonly property color input: dark ? "#1a1d25" : "#f7f8fb"
    readonly property color segOn: dark ? "#343847" : "#ffffff"
    readonly property color tipBg: dark ? "#eceef4" : "#1b1f2b"
    readonly property color tipFg: dark ? "#1b1f2b" : "#ffffff"
    readonly property color scrim: dark ? Qt.rgba(0.04, 0.05, 0.08, 0.55) : Qt.rgba(0.04, 0.05, 0.08, 0.32)
    readonly property string mono: Qt.platform.os === "windows" ? "Consolas" : "DejaVu Sans Mono"

    // cool → hot tint along the temperature axis
    readonly property var heatStops: [[0, "#38bdf8"], [0.45, "#8b7cf6"], [0.72, "#fb923c"], [1, "#f43f5e"]]
    function heat(v) {
        const x = Math.max(0, Math.min(1, v / 100))
        for (let i = 1; i < heatStops.length; i++) {
            if (x <= heatStops[i][0]) {
                const a = Qt.color(heatStops[i - 1][1]), b = Qt.color(heatStops[i][1])
                const k = (x - heatStops[i - 1][0]) / (heatStops[i][0] - heatStops[i - 1][0])
                return Qt.rgba(a.r + (b.r - a.r) * k, a.g + (b.g - a.g) * k, a.b + (b.b - a.b) * k, 1)
            }
        }
        return Qt.color(heatStops[heatStops.length - 1][1])
    }
    // Speed rings: colour follows the dial like a tachometer (requirement 5.2.3)
    readonly property var dutyStops: [[0, "#22c55e"], [0.45, "#facc15"], [0.7, "#fb923c"], [0.9, "#ef4444"], [1, "#ef4444"]]
    function duty(p) {
        const x = Math.max(0, Math.min(1, p))
        for (let i = 1; i < dutyStops.length; i++) {
            if (x <= dutyStops[i][0]) {
                const a = Qt.color(dutyStops[i - 1][1]), b = Qt.color(dutyStops[i][1])
                const k = (x - dutyStops[i - 1][0]) / (dutyStops[i][0] - dutyStops[i - 1][0])
                return Qt.rgba(a.r + (b.r - a.r) * k, a.g + (b.g - a.g) * k, a.b + (b.b - a.b) * k, 1)
            }
        }
        return Qt.color(dutyStops[dutyStops.length - 1][1])
    }
    // Probe thermometers and their temperature text: four 25 °C steps (requirement 5.3.1)
    readonly property var tempSteps: dark ? ["#60a5fa", "#facc15", "#fb923c", "#f87171"]
                                          : ["#2563eb", "#ca8a04", "#ea580c", "#dc2626"]
    function tempStep(v) { return v <= 25 ? 0 : v <= 50 ? 1 : v <= 75 ? 2 : 3 }
    function tempColor(v) { return tempSteps[tempStep(v)] }
    function alpha(c, a) { const q = Qt.color(c); return Qt.rgba(q.r, q.g, q.b, a) }
    function art(name) { return Qt.resolvedUrl("assets/art/" + name + "-" + (dark ? "dark" : "light") + ".svg") }
    function fmt1(v) { return v === null || v === undefined ? "—" : Number(v).toFixed(1) }
    function thousands(v) { return v === null || v === undefined ? "—" : Math.round(v).toLocaleString(Qt.locale("en_US"), "f", 0) }
}
