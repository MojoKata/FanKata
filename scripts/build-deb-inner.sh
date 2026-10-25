#!/bin/sh
# Runs inside ubuntu:22.04. See build-deb.sh.
set -eu
export DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
PYSIDE_VERSION=6.9.3
TOMLI_VERSION=2.2.1

apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 python3-pip ca-certificates >/dev/null

VERSION=$(python3 -c "import sys; sys.path.insert(0, 'src'); import fankata_core; print(fankata_core.__version__)")
echo "== Fankata $VERSION: unit tests on $(python3 --version)"
pip3 install -q --target /tmp/tomli "tomli==$TOMLI_VERSION"
PYTHONPATH=/tmp/tomli python3 -m unittest discover -s tests

PKG=/tmp/stage/fankata_${VERSION}_amd64
rm -rf /tmp/stage
mkdir -p "$PKG/DEBIAN" "$PKG/opt/fankata/bin" "$PKG/opt/fankata/lib" "$PKG/opt/fankata/vendor" \
         "$PKG/usr/bin" "$PKG/usr/lib/systemd/system" "$PKG/usr/share/polkit-1/actions" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/fankata"

echo "== application"
cp -r src/fankata_core src/fankatad src/fankata "$PKG/opt/fankata/lib/"
find "$PKG/opt/fankata/lib" -name __pycache__ -prune -exec rm -rf {} +
# Windows-only modules (service host, named pipe, LibreHardwareMonitor backend)
rm -f "$PKG/opt/fankata/lib/fankatad/winsvc.py" "$PKG/opt/fankata/lib/fankatad/server_win.py" \
      "$PKG/opt/fankata/lib/fankatad/backends/lhm.py" "$PKG/opt/fankata/lib/fankata_core/winfacts.py"
install -m 755 packaging/fankata-launcher.py "$PKG/opt/fankata/bin/fankata"
install -m 755 packaging/fankatad-launcher.py "$PKG/opt/fankata/bin/fankatad"
install -m 755 packaging/fankata-servicectl "$PKG/opt/fankata/bin/fankata-servicectl"
install -m 755 packaging/fankata-troubleshoot "$PKG/opt/fankata/bin/fankata-troubleshoot"
ln -s /opt/fankata/bin/fankata "$PKG/usr/bin/fankata"

echo "== vendored Python packages"
pip3 install -q --no-compile --target "$PKG/opt/fankata/vendor/core" "tomli==$TOMLI_VERSION"
pip3 install -q --no-compile --only-binary=:all: --target "$PKG/opt/fankata/vendor/gui" "PySide6-Essentials==$PYSIDE_VERSION"
G="$PKG/opt/fankata/vendor/gui"
# Prune what a QML app never loads: tools, headers, stubs, other styles, translations.
rm -rf "$G/bin" "$G"/*.dist-info/RECORD "$G/PySide6/include" "$G/PySide6/typesystems" "$G/PySide6/glue" \
       "$G/PySide6/Qt/translations" "$G/PySide6/Qt/metatypes" "$G/PySide6/Qt/libexec" "$G/PySide6/scripts" \
       "$G/PySide6/doc" "$G/PySide6/examples"
find "$G/PySide6" -maxdepth 1 \( -name '*.pyi' -o -name 'designer' -o -name 'linguist' -o -name 'assistant' \
       -o -name 'lupdate' -o -name 'lrelease' -o -name 'qml*' -o -name 'balsam*' -o -name 'rcc' -o -name 'uic' \
       -o -name 'QtDesigner*' -o -name 'QtHelp*' -o -name 'QtUiTools*' -o -name 'QtTest*' \) -exec rm -rf {} +
rm -f "$G"/PySide6/Qt/lib/libQt6Designer* "$G"/PySide6/Qt/lib/libQt6Help* "$G"/PySide6/Qt/lib/libQt6UiTools* \
      "$G"/PySide6/Qt/lib/libQt6WaylandCompositor* "$G"/PySide6/Qt/lib/libQt6QuickTest* "$G"/PySide6/Qt/lib/libQt6Test* \
      "$G"/PySide6/Qt/lib/libQt6QmlCompiler*
for style in Material Universal Imagine FluentWinUI3 Fusion macOS Windows iOS; do
    rm -rf "$G/PySide6/Qt/qml/QtQuick/Controls/$style"
done
rm -f "$G"/PySide6/Qt/lib/libQt6QuickControls2Material* "$G"/PySide6/Qt/lib/libQt6QuickControls2Universal* \
      "$G"/PySide6/Qt/lib/libQt6QuickControls2Imagine* "$G"/PySide6/Qt/lib/libQt6QuickControls2FluentWinUI3* \
      "$G"/PySide6/Qt/lib/libQt6QuickControls2Fusion*
rm -rf "$G/PySide6/Qt/qml/QtWayland/Compositor" "$G/PySide6/Qt/qml/QtTest" "$G/PySide6/Qt/plugins/designer" \
       "$G/PySide6/Qt/plugins/wayland-graphics-integration-server" "$G/PySide6/Qt/plugins/qmllint" "$G/PySide6/Qt/plugins/qmlls"
# Optional plugins and QML modules that link against libraries outside PySide6-Essentials
# (Qt3D, Pdf, VirtualKeyboard, StateMachine, SQL client libraries, CUPS) — never used here.
Q="$G/PySide6/Qt"
rm -rf "$Q/plugins/sqldrivers" "$Q/plugins/printsupport" "$Q/plugins/egldeviceintegrations/libqeglfs-kms-integration.so" \
       "$Q/plugins/imageformats/libqpdf.so" "$Q/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so" \
       "$Q/plugins/qmltooling/libqmldbg_quick3dprofiler.so" "$Q/qml/QtQml/StateMachine" "$Q/qml/QtQuick/Pdf" \
       "$Q/qml/QtQuick/Scene2D" "$Q/qml/QtQuick/Scene3D" "$Q/qml/QtQuick/VirtualKeyboard" \
       "$Q"/lib/libQt6WaylandEglCompositorHwIntegration* "$G/PySide6/QtQuickTest.abi3.so"
find "$PKG/opt/fankata/vendor" -name __pycache__ -prune -exec rm -rf {} +

echo "== system integration"
install -m 644 packaging/fankata.service "$PKG/usr/lib/systemd/system/fankata.service"
install -m 644 packaging/org.fankata.policy "$PKG/usr/share/polkit-1/actions/org.fankata.policy"
install -m 644 packaging/fankata.desktop "$PKG/usr/share/applications/fankata.desktop"
install -m 644 packaging/icons/fankata.svg "$PKG/usr/share/icons/hicolor/scalable/apps/fankata.svg"
for s in 32 48 64 128 256; do
    mkdir -p "$PKG/usr/share/icons/hicolor/${s}x${s}/apps"
    install -m 644 "packaging/icons/fankata-$s.png" "$PKG/usr/share/icons/hicolor/${s}x${s}/apps/fankata.png"
done
install -m 644 README.md "$PKG/usr/share/doc/fankata/README.md"
install -m 644 packaging/debian/copyright "$PKG/usr/share/doc/fankata/copyright"
install -m 755 packaging/debian/postinst packaging/debian/prerm packaging/debian/postrm "$PKG/DEBIAN/"

SIZE=$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" packaging/debian/control.in > "$PKG/DEBIAN/control"
find "$PKG" -type d -exec chmod 755 {} +

echo "== dpkg-deb"
OUT=releases/fankata_${VERSION}_amd64.deb
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$OUT"
(cd releases && sha256sum "fankata_${VERSION}_amd64.deb" > "fankata_${VERSION}_amd64.deb.sha256")
chown "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT" "$OUT.sha256"
dpkg-deb --info "$OUT" | sed -n '1,12p'
ls -l "$OUT"
cat "$OUT.sha256"
