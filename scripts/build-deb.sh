#!/bin/sh
# Build the Fankata .deb inside an Ubuntu 22.04 container (the oldest supported
# release), then write releases/fankata_<version>_amd64.deb and its .sha256.
#   scripts/build-deb.sh
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${FANKATA_BUILD_IMAGE:-ubuntu:22.04}
mkdir -p "$HERE/releases"
docker run --rm -v "$HERE:/src" -w /src -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    "$IMAGE" sh /src/scripts/build-deb-inner.sh
