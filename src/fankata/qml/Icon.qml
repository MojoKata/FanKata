import QtQuick
import QtQuick.Shapes
import "."
import "Icons.js" as Icons

Item {
    id: root
    property string name
    property color color: Theme.text
    property real size: 16
    property real lineWidth: 1.6
    implicitWidth: size
    implicitHeight: size
    width: size
    height: size

    Shape {
        width: 16
        height: 16
        scale: root.size / 16
        transformOrigin: Item.TopLeft
        ShapePath {
            strokeColor: root.color
            strokeWidth: root.lineWidth * 16 / root.size
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: Icons.stroke(root.name) }
        }
        ShapePath {
            strokeColor: "transparent"
            strokeWidth: 0
            fillColor: root.color
            PathSvg { path: Icons.fill(root.name) }
        }
    }
}
