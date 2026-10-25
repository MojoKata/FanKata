#!/bin/sh
# Run Fankata against simulated hardware: fake sysfs + fankatad + GUI, all unprivileged.
#   scripts/demo.sh                 interactive demo
#   scripts/demo.sh --tour DIR      save screenshots of every screen and exit
# Needs PySide6 importable by $PYTHON (default python3), e.g. from a venv.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/fankata-demo.XXXXXX")
cleanup() { kill $SIM $SVC 2>/dev/null || true; wait 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM
export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"
export XDG_CONFIG_HOME="$WORK/xdg"
mkdir -p "$WORK/etc"
cp "$HERE/scripts/demo/config.toml" "$WORK/etc/config.toml"
"$PY" "$HERE/tests/fakesysfs.py" "$WORK/root" --simulate & SIM=$!
sleep 0.5
"$PY" -m fankatad --sysfs-root "$WORK/root" --config "$WORK/etc/config.toml" --run-dir "$WORK/run" \
      --socket "$WORK/fankata.sock" --no-auth & SVC=$!
sleep 1
"$PY" -m fankata --socket "$WORK/fankata.sock" --sysfs-root "$WORK/root" --config "$WORK/etc/config.toml" "$@"
