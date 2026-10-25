import QtQuick

// Edge and corner handles for the frameless window.
Item {
    id: root
    property var window: null
    anchors.fill: parent
    readonly property int m: 6
    z: 1000
    Repeater {
        model: [
            [Qt.LeftEdge, Qt.SizeHorCursor], [Qt.RightEdge, Qt.SizeHorCursor],
            [Qt.TopEdge, Qt.SizeVerCursor], [Qt.BottomEdge, Qt.SizeVerCursor],
            [Qt.LeftEdge | Qt.TopEdge, Qt.SizeFDiagCursor], [Qt.RightEdge | Qt.BottomEdge, Qt.SizeFDiagCursor],
            [Qt.RightEdge | Qt.TopEdge, Qt.SizeBDiagCursor], [Qt.LeftEdge | Qt.BottomEdge, Qt.SizeBDiagCursor]]
        MouseArea {
            readonly property int e: modelData[0]
            readonly property bool l: e & Qt.LeftEdge
            readonly property bool r: e & Qt.RightEdge
            readonly property bool t: e & Qt.TopEdge
            readonly property bool b: e & Qt.BottomEdge
            x: r ? root.width - root.m * (t || b ? 2 : 1) : 0
            y: b ? root.height - root.m * (l || r ? 2 : 1) : 0
            width: (l || r) ? root.m * (t || b ? 2 : 1) : root.width
            height: (t || b) ? root.m * (l || r ? 2 : 1) : root.height
            cursorShape: modelData[1]
            onPressed: if (root.window) root.window.startSystemResize(e)
        }
    }
}
