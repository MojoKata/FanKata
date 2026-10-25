.pragma library
// 16-unit icon paths (from the mockups). Circles and rounded rects are expanded to path data.
function circle(cx, cy, r) {
    return `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`
}
function rrect(x, y, w, h, r) {
    return `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}` +
           `H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`
}
const S = {
    fan: "M8 8C8 4.2 9.6 2 11.6 2.6C13.2 3.6 11.8 6.6 8 8Z M8 8C4.7 9.9 2 9.6 2 7.5C2.5 5.8 5.7 5.3 8 8Z M8 8C11.3 9.9 12.1 12.4 10.4 13.7C8.5 14.2 7.1 11.2 8 8Z",
    curve: "M2 2V14H14 M4 12C8 12 8.5 5 13.5 4",
    thermo: "M6.5 9.3V3.6a1.5 1.5 0 0 1 3 0V9.3 " + circle(8, 11.6, 2.6),
    chevDown: "M4 6L8 10L12 6", chevRight: "M6 4L10 8L6 12", chevLeft: "M10 4L6 8L10 12",
    plus: "M8 3V13M3 8H13", x: "M4 4L12 12M12 4L4 12",
    pencil: "M10.5 2.5L13.5 5.5L5.5 13.5H2.5V10.5Z",
    panel: rrect(1.8, 2.8, 12.4, 10.4, 2) + " M10 3V13",
    check: "M3 8.5L6.5 12L13 4.5",
    warn: "M8 2L14.5 13.5H1.5Z M8 6.3V9.3",
    trash: "M3 4.5H13M6 4.5V2.8H10V4.5M4.5 4.5L5.3 13.5H10.7L11.5 4.5",
    copy: rrect(5, 5, 9, 9, 1.6) + " M3 11V3.6A1.6 1.6 0 0 1 4.6 2H11",
    refresh: "M13 8A5 5 0 1 1 11.5 4.4 M11.8 1.8V4.8H8.8",
    pulse: "M1.5 11H4.5V5H8V11H11.5V5H14.5",
    info: circle(8, 8, 6) + " M8 7.2V11",
    lifebuoy: circle(8, 8, 6) + " " + circle(8, 8, 2.6) + " M3.8 3.8L6.2 6.2M12.2 3.8L9.8 6.2M3.8 12.2L6.2 9.8M12.2 12.2L9.8 9.8",
    lock: rrect(3, 7, 10, 7, 1.6) + " M5.5 7V5a2.5 2.5 0 0 1 5 0V7",
    bang: "M8 3.5V9",
    link: "M9 3H13V7M13 3L7.5 8.5M11 9.5V13H3V5H6.5",
}
const F = {
    dots: circle(8, 3, 1.25) + circle(8, 8, 1.25) + circle(8, 13, 1.25),
    more: circle(3, 8, 1.3) + circle(8, 8, 1.3) + circle(13, 8, 1.3),
    warn: circle(8, 11.5, 0.7),
    info: circle(8, 5, 0.8),
    bang: circle(8, 12, 0.8),
}
function stroke(name) { return S[name] || "M0 0" }
function fill(name) { return F[name] || "M0 0" }
