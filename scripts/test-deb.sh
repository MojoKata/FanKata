#!/bin/sh
# Install the built .deb on each target release in a container and smoke-test it.
#   scripts/test-deb.sh                          all targets
#   FANKATA_TEST_IMAGES="ubuntu:24.04" scripts/test-deb.sh
# The first image also saves screenshots of the installed app to
# screenshots/linux/dark/ and screenshots/linux/light/.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
IMAGES=${FANKATA_TEST_IMAGES:-"ubuntu:22.04 ubuntu:24.04 linuxmintd/mint21.3-amd64 linuxmintd/mint22.1-amd64"}
DEB=$(ls -t "$HERE"/releases/fankata_*_amd64.deb | head -1)
echo "testing $(basename "$DEB")"
first=1
for img in $IMAGES; do
    shots=""
    [ $first = 1 ] && shots=screenshots
    first=0
    echo "================ $img"
    docker run --rm -v "$HERE:/src" -w /src -e DEB="releases/$(basename "$DEB")" -e SHOTS="$shots" \
        -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" "$img" sh /src/scripts/test-deb-inner.sh
done
echo "all targets passed"
