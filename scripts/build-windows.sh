#!/bin/sh
# Build the Windows installer on Linux: PyInstaller under Wine (tobix/pywine),
# then Inno Setup under Wine (amake/innosetup). Writes
# releases/Fankata-<version>-setup.exe and its .sha256.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEPS="$HERE/build/windows-deps"
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$HERE/src'); import fankata_core; print(fankata_core.__version__)")
LHM_URL=https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip
LHM_SHA=086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001
PAWNIO_URL=https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe
PAWNIO_SHA=1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032

fetch() {   # url file sha256
    [ -f "$2" ] || curl -sSL -o "$2" "$1"
    echo "$3  $2" | sha256sum -c --quiet || { echo "checksum mismatch: $2"; rm -f "$2"; exit 1; }
}
mkdir -p "$DEPS" "$HERE/releases" "$HERE/build/wine-cache"
fetch "$LHM_URL" "$DEPS/LibreHardwareMonitor-0.9.6.zip" "$LHM_SHA"
fetch "$PAWNIO_URL" "$DEPS/PawnIO_setup.exe" "$PAWNIO_SHA"
# LibreHardwareMonitorLib and its dependencies only (not the LibreHardwareMonitor app)
rm -rf "$DEPS/lhm"; mkdir -p "$DEPS/lhm"
(cd "$DEPS/lhm" && unzip -q -o ../LibreHardwareMonitor-0.9.6.zip '*.dll' -x 'Aga.Controls.dll' 'OxyPlot*' \
    'Microsoft.Win32.TaskScheduler*' '*/Microsoft.Win32.TaskScheduler.resources.dll')

echo "== PyInstaller (Wine)"
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$HERE:/src" -v "$HERE/build/wine-cache:/cache" -w /src tobix/pywine:3.12 sh -c '
  wine python -m pip install -q --cache-dir Z:\\cache pyinstaller==6.16.0 PySide6-Essentials==6.9.3 pywin32==312 pythonnet==3.2.0 >/dev/null 2>&1
  wine python -m PyInstaller --noconfirm --clean --log-level WARN \
       --distpath Z:\\src\\build\\windows\\dist --workpath Z:\\src\\build\\windows\\work packaging\\windows\\fankata.spec
' 2>&1 | grep -vE "^(wine|[0-9a-f]{4}:(fixme|err|warn))" | grep -v "^$" || true
test -f "$HERE/build/windows/dist/Fankata/fankata.exe" && test -f "$HERE/build/windows/dist/Fankata/fankatad.exe"

# the containers run as root: hand the outputs back to the invoking user
docker run --rm -v "$HERE:/src" tobix/pywine:3.12 sh -c "chown -R $(id -u):$(id -g) /src/build /src/releases; find /src/src -name __pycache__ -prune -exec rm -rf {} +" >/dev/null 2>&1 || true

echo "== Inno Setup (Wine)"
docker run --rm -v "$HERE:/work" -w /work/packaging/windows amake/innosetup "/DAppVersion=$VERSION" fankata.iss 2>&1 | tail -3
OUT="Fankata-$VERSION-setup.exe"
chgrp "$(id -g)" "$HERE/releases/$OUT" 2>/dev/null || true
(cd "$HERE/releases" && sha256sum "$OUT" > "$OUT.sha256" && ls -l "$OUT" && cat "$OUT.sha256")
