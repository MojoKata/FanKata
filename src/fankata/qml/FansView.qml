import QtQuick
import "."

// Fans grouped by Probe (requirement 5.3). Tiles are created once per fan and
// animate to their layout position, so a Probe change glides a tile into its new
// group. Tiles can be dragged to reorder within a group or to move to another.
Item {
    id: root
    property string selected: ""
    property string filter: "all"          // all | managed | unmanaged
    signal message(string text)
    signal troubleshootRequested()
    function emptyText() {
        const temps = [...new Set(backend.probes.filter(p => p.kind === "system").map(p => (p.desc || "").split(" · ").pop()).filter(s => s))]
        if (Qt.platform.os === "windows")
            return backend.connected ? "LibreHardwareMonitor found no fan control on this PC. The troubleshooter can check the driver and other fan software."
                                     : "Fan control is off, so Fankata can’t see the fans. The troubleshooter can check why."
        return (temps.length ? "Fankata found temperatures from " + temps.slice(0, 4).join(", ") + ", but no fan control. "
                             : "Fankata found no fan control. ") + "The board’s sensor driver may not be loaded."
    }
    property alias detail: detailPanel

    // --- data ---------------------------------------------------------------------
    readonly property var fans: backend.fans
    property var fanIds: []
    property var fanMap: ({})
    onFansChanged: sync()
    Component.onCompleted: sync()
    function sync() {
        const m = {}
        for (const f of fans) m[f.id] = f
        fanMap = m
        const ids = fans.map(f => f.id)
        if (ids.join("|") !== fanIds.join("|")) fanIds = ids
        if (ids.length && !animate) settle.start()
    }
    readonly property var selectedFan: fanMap[selected] || null
    readonly property bool panelOpen: selectedFan !== null
    readonly property int managedCount: fans.filter(f => f.managed).length
    readonly property var probeMap: { const m = {}; for (const p of backend.probes) m[p.name] = p; return m }
    readonly property var probeOrder: backend.probes.map(p => p.name)
    readonly property var headerKeys: probeOrder.concat([""])
    readonly property var order: backend.prefs.fanOrder || []
    function keyOf(f) { return f && f.curve && f.probe ? f.probe : "" }
    function shownKey(k) { return filter === "all" || (filter === "managed") === (k !== "") }

    // --- layout -------------------------------------------------------------------
    readonly property real gap: 20
    readonly property real headerH: 48
    readonly property real gridW: Math.max(300, viewport.width - 64)
    // Tiles behave like a CSS flex row with flex: 1 and max-width: 33% (requirement 5.2.5):
    // up to three share a row equally, scaling from their designed 380 × 290 up to 2×
    // (760 × 580) with the aspect ratio kept. A tile never gets narrower than 360 px (the
    // previous minimum); narrower rows hold fewer tiles instead.
    readonly property real baseW: 380
    readonly property real baseH: 290
    readonly property real minW: 360
    readonly property int cols: Math.max(1, Math.min(3, Math.floor((gridW + gap) / (minW + gap))))
    readonly property real cardW: Math.min(2 * baseW, (gridW - (cols - 1) * gap) / cols)
    readonly property real cardH: cardW * baseH / baseW
    property bool animate: false
    Timer { id: settle; interval: 400; onTriggered: root.animate = true }

    function rank(a, b) {
        const ia = order.indexOf(a), ib = order.indexOf(b)
        if (ia >= 0 && ib >= 0) return ia - ib
        if (ia >= 0) return -1
        if (ib >= 0) return 1
        return (fanMap[a] ? fanMap[a].name : a).localeCompare(fanMap[b] ? fanMap[b].name : b)
    }
    // Group ids by probe. exclude: the dragged fan; keep: keys shown even when empty.
    function groupsFor(exclude, target, index, keep) {
        const g = {}
        for (const f of fans) {
            if (f.id === exclude) continue
            const k = keyOf(f)
            if (!shownKey(k) && !(keep || []).includes(k)) continue
            ;(g[k] = g[k] || []).push(f.id)
        }
        for (const k of keep || []) g[k] = g[k] || []
        for (const k in g) g[k].sort(rank)
        if (exclude && target !== null && target !== undefined) {
            g[target] = g[target] || []
            g[target].splice(Math.max(0, Math.min(index, g[target].length)), 0, exclude)
        }
        const keys = Object.keys(g).sort((a, b) => (a === "") - (b === "") || probeOrder.indexOf(a) - probeOrder.indexOf(b))
        return { g: g, keys: keys }
    }
    function place(gk) {
        const pos = {}, heads = {}
        let y = 12
        for (const k of gk.keys) {
            const ids = gk.g[k]
            const h = { y: y, count: ids.filter(id => id !== dragId).length }
            y += headerH
            h.tilesTop = y
            ids.forEach((id, i) => pos[id] = { x: (i % cols) * (cardW + gap), y: y + Math.floor(i / cols) * (cardH + gap) })
            h.bottom = y + Math.max(1, Math.ceil(ids.length / cols)) * (cardH + gap) - gap
            heads[k] = h
            y = h.bottom + 32
        }
        return { pos: pos, heads: heads, keys: gk.keys, height: y, groups: gk.g }
    }
    readonly property var layout: dragId !== "" ? place(groupsFor(dragId, dragTarget, dragIndex, dragKeep))
                                                : place(groupsFor("", null, 0, []))

    // --- dragging -----------------------------------------------------------------
    property string dragId: ""
    property string dragOrigin: ""
    property string dragTarget: ""
    property int dragIndex: 0
    property var dragKeep: []
    property var frozen: null
    property real dragCX: 0
    property real dragCY: 0
    property real startCX: 0
    property real startCY: 0
    property real startScroll: 0
    property real lastTX: 0
    property real lastTY: 0

    function beginDrag(id, cx, cy) {
        const f = fanMap[id]
        dragOrigin = keyOf(f)
        dragKeep = [dragOrigin, ""]
        const gk = groupsFor(id, null, 0, dragKeep)
        frozen = place(gk)
        const cur = layout.groups[dragOrigin] || []
        dragIndex = Math.max(0, cur.indexOf(id))
        dragTarget = dragOrigin
        startCX = cx; startCY = cy; dragCX = cx; dragCY = cy
        startScroll = scrollY; lastTX = 0; lastTY = 0
        dragId = id
    }
    function moveDrag(tx, ty) {
        lastTX = tx; lastTY = ty
        dragCX = startCX + tx
        dragCY = startCY + ty + (scrollY - startScroll)
        const hit = hitTest(dragCX, dragCY)
        dragTarget = hit.key
        dragIndex = hit.index
    }
    function hitTest(cx, cy) {
        const L = frozen
        let key = L.keys[0]
        for (const k of L.keys) if (cy >= L.heads[k].y - 20) key = k
        const h = L.heads[key], n = L.groups[key].length
        const col = Math.max(0, Math.min(cols - 1, Math.floor(cx / (cardW + gap))))
        const row = Math.max(0, Math.floor((cy - h.tilesTop + gap / 2) / (cardH + gap)))
        return { key: key, index: Math.max(0, Math.min(n, row * cols + col)) }
    }
    function nearestIn(key, cx, cy) {
        let best = "", bd = 1e12
        for (const id of (frozen && frozen.groups[key]) || []) {
            const p = frozen.pos[id], dx = p.x + cardW / 2 - cx, dy = p.y + cardH / 2 - cy
            if (dx * dx + dy * dy < bd && fanMap[id] && fanMap[id].curve) { bd = dx * dx + dy * dy; best = id }
        }
        return best
    }
    function dropHint() {
        if (dragId === "" || dragTarget === dragOrigin) return ""
        if (dragTarget === "") return "Drop to return it to system default"
        if (dragOrigin === "") {
            const n = nearestIn(dragTarget, dragCX, dragCY)
            return n ? "Drop to use " + dragTarget + "  ·  takes the " + fanMap[n].curve + " curve from " + fanMap[n].name + " (nearest)"
                     : "Drop to use " + dragTarget
        }
        return "Drop to use " + dragTarget
    }
    function endDrag(apply) {
        if (dragId === "") return
        const id = dragId, target = dragTarget, origin = dragOrigin
        if (apply) {
            const gk = groupsFor(id, target, dragIndex, dragKeep)
            let seq = []
            for (const k of gk.keys) seq = seq.concat(gk.g[k])
            for (const x of order) if (seq.indexOf(x) < 0) seq.push(x)
            backend.setPref("fanOrder", seq)
            let err = ""
            if (target !== origin) {
                if (target === "") err = backend.setFanCurve(id, "")
                else if (origin === "") {
                    const n = nearestIn(target, dragCX, dragCY)
                    err = backend.setFanAssignment(id, n ? fanMap[n].curve : "", target)
                } else err = backend.setFanProbe(id, target)
            }
            if (err) root.message(err)
        }
        dragId = ""
        frozen = null
    }
    Timer {      // scroll while dragging near the top or bottom edge
        interval: 16; repeat: true; running: root.dragId !== ""
        onTriggered: {
            const vy = root.dragCY - root.scrollY
            let d = 0
            if (vy < 90) d = -Math.min(18, (90 - vy) / 4)
            else if (vy > viewport.height - 90) d = Math.min(18, (vy - viewport.height + 90) / 4)
            if (d !== 0) { root.scrollTo(root.scrollY + d); root.moveDrag(root.lastTX, root.lastTY) }
        }
    }

    // --- scrolling (wheel only, so dragging a tile never fights a flick) ----------
    property real scrollY: 0
    readonly property real maxScroll: Math.max(0, layout.height - viewport.height)
    onMaxScrollChanged: if (scrollY > maxScroll) scrollY = maxScroll
    function scrollTo(v) { scrollY = Math.max(0, Math.min(maxScroll, v)) }

    Item {
        id: main
        anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
        anchors.right: root.panelOpen ? detailPanel.left : parent.right
        Text { id: title; x: 32; y: 30; text: "Fans"; color: Theme.text; font.pixelSize: 28; font.bold: true }
        Text {
            anchors.left: title.right; anchors.leftMargin: 16; anchors.baseline: title.baseline
            text: root.fans.length + " detected  ·  " + root.managedCount + " managed by Fankata"
            color: Theme.muted; font.pixelSize: 14
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: root.panelOpen ? 28 : 32
            y: 28; spacing: 8
            Repeater {
                model: [["all", "All"], ["managed", "Managed"], ["unmanaged", "Unmanaged"]]
                Rectangle {
                    readonly property bool on: root.filter === modelData[0]
                    height: 30; radius: 15; width: t.implicitWidth + 24
                    color: on ? Theme.accentSoft : "transparent"
                    border.width: on ? 0 : 1; border.color: Theme.border
                    Text { id: t; anchors.centerIn: parent; text: modelData[1]; color: parent.on ? Theme.accent : Theme.muted; font.pixelSize: 13; font.bold: true }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.filter = modelData[0] }
                }
            }
        }
        Item {
            id: viewport
            anchors.fill: parent; anchors.topMargin: 78
            clip: true
            // The software renderer doesn't clip Shape nodes (the icons); a layer does.
            layer.enabled: GraphicsInfo.api === GraphicsInfo.Software
            Rectangle { anchors.fill: parent; color: Theme.bg }   // layers need an opaque backing
            WheelHandler {
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: event => root.scrollTo(root.scrollY - (event.pixelDelta.y !== 0 ? event.pixelDelta.y : event.angleDelta.y / 120 * 80))
            }
            Item {
                id: content
                objectName: "fanContent"
                x: 32; y: -root.scrollY
                width: root.gridW; height: root.layout.height

                // group headers: the Probe pill (or "Unmanaged fans")
                Repeater {
                    model: root.headerKeys
                    Item {
                        id: head
                        readonly property string key: modelData
                        readonly property var h: root.layout.heads[key]
                        readonly property var probe: root.probeMap[key]
                        readonly property bool lit: root.dragId !== "" && root.dragTarget === key && key !== root.dragOrigin
                        readonly property string hint: lit ? root.dropHint() : ""
                        visible: !!h
                        width: root.gridW; height: 32
                        y: h ? h.y : 0
                        Behavior on y { enabled: root.animate; NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }
                        Rectangle {
                            visible: head.lit
                            x: -5; y: -5; width: pill.width + 10; height: 42; radius: 21
                            color: Theme.alpha(Theme.accent, 0.22)
                        }
                        Rectangle {
                            id: pill
                            height: 32; radius: 16
                            width: pillRow.implicitWidth + 28
                            color: head.lit ? Theme.accentSoft : Theme.surface
                            border.width: head.lit ? 2 : 1
                            border.color: head.lit ? Theme.accent : Theme.border
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Row {
                                id: pillRow
                                x: 14; anchors.verticalCenter: parent.verticalCenter
                                spacing: 8
                                Thermometer {
                                    visible: !!head.key
                                    value: head.probe ? head.probe.value : null
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Icon {
                                    visible: !head.key
                                    name: "fan"; anchors.verticalCenter: parent.verticalCenter
                                    color: head.lit ? Theme.accent : Theme.faint
                                }
                                Text {
                                    text: head.key || "Unmanaged fans"
                                    color: head.lit ? Theme.accent : head.key ? Theme.text : Theme.muted
                                    font.pixelSize: 13; font.bold: true
                                    font.family: head.key ? Theme.mono : Qt.application.font.family
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Text {
                                    visible: !!head.key
                                    text: head.probe ? Theme.fmt1(head.probe.value) + "°" : ""
                                    color: head.probe && head.probe.value !== null && head.probe.value !== undefined ? Theme.tempColor(head.probe.value) : Theme.faint
                                    font.pixelSize: 13; font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                        Text {
                            id: desc
                            anchors.left: pill.right; anchors.leftMargin: 14; anchors.verticalCenter: pill.verticalCenter
                            readonly property int n: head.h ? head.h.count : 0
                            readonly property bool custom: !!head.probe && head.probe.kind === "custom"
                            text: head.hint || ((head.key ? (head.probe ? head.probe.desc : "") : "System default") + "  ·  " + n + (n === 1 ? " fan" : " fans"))
                            color: head.hint ? Theme.accent : Theme.muted
                            font.pixelSize: 12; font.bold: !!head.hint
                            font.family: custom && !head.hint ? Theme.mono : Qt.application.font.family
                            width: Math.min(implicitWidth, head.width - pill.width - 30); elide: Text.ElideRight
                        }
                        Rectangle {
                            x: desc.x + desc.width + 16; anchors.verticalCenter: pill.verticalCenter
                            width: Math.max(0, head.width - x); height: head.lit ? 1.5 : 1
                            color: head.lit ? Theme.accent : Theme.border
                        }
                    }
                }

                // where the dragged tile will land
                Rectangle {
                    readonly property var p: root.dragId !== "" ? root.layout.pos[root.dragId] : null
                    visible: !!p
                    x: p ? p.x : 0; y: p ? p.y : 0
                    width: root.cardW; height: root.cardH; radius: 18 * root.cardW / root.baseW
                    color: Theme.alpha(Theme.accent, Theme.dark ? 0.12 : 0.08)
                    border.color: Theme.accent; border.width: 2
                    Behavior on x { enabled: root.animate; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                    Behavior on y { enabled: root.animate; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }

                // tiles
                Repeater {
                    model: root.fanIds
                    Item {
                        id: tile
                        readonly property string fid: modelData
                        readonly property var fan: root.fanMap[fid] || null
                        readonly property var p: root.layout.pos[fid]
                        readonly property bool dragging: root.dragId === fid
                        visible: !!p || dragging
                        width: root.cardW; height: root.cardH
                        x: dragging ? root.dragCX - width / 2 : (p ? p.x : 0)
                        y: dragging ? root.dragCY - height / 2 : (p ? p.y : 0)
                        z: dragging ? 10 : 1
                        rotation: dragging ? -2 : 0
                        scale: dragging ? 1.02 : 1
                        Behavior on x { enabled: root.animate && !tile.dragging; NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }
                        Behavior on y { enabled: root.animate && !tile.dragging; NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }
                        Behavior on rotation { NumberAnimation { duration: 150 } }
                        Behavior on scale { NumberAnimation { duration: 150 } }
                        FanCard {
                            anchors.fill: parent
                            fan: tile.fan
                            lifted: tile.dragging
                            selected: tile.fid === root.selected
                            onClicked: root.selected = (root.selected === tile.fid ? "" : tile.fid)
                        }
                        DragHandler {
                            id: dh
                            target: null
                            enabled: backend.connected
                            cursorShape: active ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                            onActiveChanged: {
                                if (active) root.beginDrag(tile.fid, tile.x + tile.width / 2, tile.y + tile.height / 2)
                                else root.endDrag(true)
                            }
                            onActiveTranslationChanged: if (active) root.moveDrag(activeTranslation.x, activeTranslation.y)
                        }
                    }
                }
            }
            Rectangle {     // scroll indicator
                visible: root.maxScroll > 0
                anchors.right: parent.right; anchors.rightMargin: 4
                width: 4; radius: 2; color: Theme.borderStrong; opacity: 0.8
                height: Math.max(40, viewport.height * viewport.height / root.layout.height)
                y: root.maxScroll > 0 ? (viewport.height - height) * root.scrollY / root.maxScroll : 0
            }
            Rectangle {     // nothing to control: offer the troubleshooter (requirement 5.1.3)
                id: emptyCard
                objectName: "emptyCard"
                visible: root.fans.length === 0
                width: Math.min(560, viewport.width - 64); height: emptyCol.height + 64
                x: Math.round((viewport.width - width) / 2); y: Math.round(Math.max(20, (viewport.height - height) / 2 - 40))
                radius: 22; color: Theme.surface; border.color: Theme.border
                Column {
                    id: emptyCol
                    y: 32; width: parent.width - 64; x: 32; spacing: 12
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 88; height: 88; radius: 44; color: Theme.illusOff; border.color: Theme.border
                        Icon { anchors.centerIn: parent; name: "fan"; size: 48; lineWidth: 1.4; color: Theme.faint }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; topPadding: 6; text: "No controllable fans found"; color: Theme.text; font.pixelSize: 19; font.bold: true }
                    Text {
                        width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                        color: Theme.muted; font.pixelSize: 14; lineHeight: 1.2
                        text: root.emptyText()
                    }
                    Item { width: 1; height: 4 }
                    FButton {
                        objectName: "troubleshootButton"
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitHeight: 40; primary: true; icon: "lifebuoy"; text: "Troubleshoot"
                        onClicked: root.troubleshootRequested()
                    }
                }
            }
        }
    }
    FanDetail {
        id: detailPanel
        visible: root.panelOpen
        anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        width: 450
        fan: root.selectedFan
        onCloseRequested: root.selected = ""
        onMessage: text => root.message(text)
    }

    // --- screenshot tour hook: show a drag in progress without a pointer ----------
    function demoDrag(name, target, index, offX, offY, scroll) {
        const f = fans.find(x => x.name === name)
        if (!f) return
        const p = layout.pos[f.id]
        beginDrag(f.id, p.x + cardW / 2, p.y + cardH / 2)
        dragTarget = target
        dragIndex = index
        const q = place(groupsFor(f.id, target, index, dragKeep)).pos[f.id]
        dragCX = q.x + cardW / 2 + offX
        dragCY = q.y + cardH / 2 + offY
        scrollTo(scroll)
    }
    function demoDragEnd() { endDrag(false) }
    // for tests/gui_drag.py: points in window coordinates
    function tilePoint(name, fx, fy) {
        const f = fans.find(x => x.name === name)
        const p = f ? layout.pos[f.id] : null
        return p ? content.mapToItem(null, p.x + cardW * fx, p.y + cardH * fy) : Qt.point(-1, -1)
    }
    function slotPoint(key, index, fx, fy) {
        const h = layout.heads[key]
        if (!h) return Qt.point(-1, -1)
        return content.mapToItem(null, (index % cols) * (cardW + gap) + cardW * fx,
                                 h.tilesTop + Math.floor(index / cols) * (cardH + gap) + cardH * fy)
    }
}
