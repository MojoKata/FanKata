#!/bin/sh
# Runs inside each target container. See test-deb.sh.
set -eu
export DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
apt-get update -qq
apt-get install -y -qq "./$DEB" fonts-dejavu-core >/tmp/apt.log 2>&1 || { tail -40 /tmp/apt.log; exit 1; }
. /etc/os-release
echo "== installed on $PRETTY_NAME with $(python3 --version)"

echo "== shared libraries"
# The GTK3 platform theme is the one optional plugin kept: desktops always have GTK 3.
missing=$(find /opt/fankata/vendor/gui/PySide6 -name '*.so*' -type f ! -name libqgtk3.so -exec ldd {} + 2>/dev/null | grep 'not found' | sort -u || true)
if [ -n "$missing" ]; then echo "missing:"; echo "$missing"; exit 1; fi
echo "all resolved"

/opt/fankata/bin/fankatad --version
fankata --version

echo "== systemd unit"
apt-get install -y -qq systemd >/dev/null 2>&1 || true
if command -v systemd-analyze >/dev/null; then
    systemd-analyze verify /usr/lib/systemd/system/fankata.service && echo "unit ok"
fi

echo "== service against simulated hardware (as root, like systemd runs it)"
W=/tmp/fankata-test
rm -rf $W; mkdir -p $W/etc
cp scripts/demo/config.toml $W/etc/config.toml
python3 tests/fakesysfs.py $W/root --simulate & SIM=$!
sleep 0.5
/opt/fankata/bin/fankatad --sysfs-root $W/root --config $W/etc/config.toml --run-dir $W/run --socket $W/fankata.sock & SVC=$!
sleep 1.5
python3 - "$W" <<'PY'
import json, socket, sys
w = sys.argv[1]
s = socket.socket(socket.AF_UNIX); s.connect(f"{w}/fankata.sock"); f = s.makefile("rwb")
def ask(**m):
    f.write((json.dumps(m) + "\n").encode()); f.flush(); return json.loads(f.readline())
assert ask(id=1, cmd="hello", version=1)["result"]["compatible"]
st = ask(id=2, cmd="get_state")["result"]
fans = {x["id"]: x for x in st["fans"]}
assert len(fans) == 6, fans.keys()
assert fans["nct6798:pwm2"]["managed"] and fans["nct6798:pwm2"]["status"] == "managed", fans["nct6798:pwm2"]
assert not fans["nct6798:pwm3"]["managed"]
en = open(f"{w}/root/sys/devices/platform/nct6775.656/hwmon/hwmon3/pwm2_enable").read().strip()
assert en == "1", en
print("protocol ok:", ", ".join(f"{x['name']} {x['duty']}%" for x in st["fans"]))
PY

echo "== GUI"
export XDG_CONFIG_HOME=$W/xdg XDG_RUNTIME_DIR=$W/xdg-run
mkdir -p $XDG_RUNTIME_DIR; chmod 700 $XDG_RUNTIME_DIR
if [ -n "$SHOTS" ]; then themes="dark light"; else themes="dark"; fi
for theme in $themes; do
    if [ -n "$SHOTS" ]; then dir="/src/$SHOTS/linux/$theme"; else dir="$W/shots/$theme"; fi
    rm -rf "$dir"; mkdir -p "$dir"
    warm=0; [ -n "$SHOTS" ] && warm=45       # screenshots: 45 s of real probe history for the sparklines
    fankata --socket $W/fankata.sock --sysfs-root $W/root --theme $theme --tour "$dir" --tour-warmup $warm 2>$W/gui.log | tail -1
    if grep -E "qml|QML|Error|Traceback" $W/gui.log; then echo "GUI warnings"; exit 1; fi
    n=$(ls "$dir" | wc -l)
    [ "$n" -ge 13 ] || { echo "expected 13 $theme screens, got $n"; exit 1; }
    echo "$theme screens rendered: $n"
    [ -n "$SHOTS" ] && chown -R "$HOST_UID:$HOST_GID" "/src/$SHOTS/linux"
done

echo "== stop restores defaults"
kill -TERM $SVC; wait $SVC || true
en=$(cat $W/root/sys/devices/platform/nct6775.656/hwmon/hwmon3/pwm2_enable)
[ "$en" = "5" ] || { echo "pwm2_enable is $en, expected 5 (firmware)"; exit 1; }
echo "pwm2 back to firmware mode 5"

echo "== app with the service off (read-only)"
for theme in $themes; do
    if [ -n "$SHOTS" ]; then dir="/src/$SHOTS/linux/$theme"; else dir="$W/shots/$theme"; fi
    fankata --socket $W/fankata.sock --sysfs-root $W/root --config $W/etc/config.toml --theme $theme \
            --tour "$dir" --tour-only 12-service-off 2>$W/gui.log | tail -1
    if grep -E "qml|QML|Error|Traceback" $W/gui.log; then echo "GUI warnings"; exit 1; fi
    test -f "$dir/12-service-off.png" && echo "$theme: 12-service-off"
    [ -n "$SHOTS" ] && chown -R "$HOST_UID:$HOST_GID" "/src/$SHOTS/linux"
done

echo "== a PC with no fan control: empty Fans view and Troubleshoot fans"
mkdir -p $W/empty
for theme in $themes; do
    if [ -n "$SHOTS" ]; then dir="/src/$SHOTS/linux/$theme"; else dir="$W/shots/$theme"; fi
    fankata --socket $W/none.sock --sysfs-root $W/empty --config $W/etc/config.toml --theme $theme \
            --tour "$dir" --tour-only 16-fans-empty,19-troubleshoot-tips 2>$W/gui.log | tail -1
    if grep -E "qml|QML|Error|Traceback" $W/gui.log; then echo "GUI warnings"; exit 1; fi
    test -f "$dir/16-fans-empty.png" && test -f "$dir/19-troubleshoot-tips.png" && echo "$theme: 16-fans-empty, 19-troubleshoot-tips"
    [ -n "$SHOTS" ] && chown -R "$HOST_UID:$HOST_GID" "/src/$SHOTS/linux"
done

echo "== fankata-troubleshoot (the root half of Troubleshoot fans)"
grep -q 'org.fankata.troubleshoot' /usr/share/polkit-1/actions/org.fankata.policy && echo "polkit action installed"
out=$(/opt/fankata/bin/fankata-troubleshoot load ../evil || true)
printf "%s\n" "$out" | grep -q '"ok": false' || { echo "helper loaded a bad module name: $out"; exit 1; }
cat > $W/fakebin-sd <<'SD'
#!/bin/sh
cat <<'OUT'
Now follows a summary of the probes I have just done.
Just press ENTER to continue:
Driver `nct6775':
  * ISA bus, address 0x290
    Chip `Nuvoton NCT6798D Super IO Sensors' (confidence: 9)
OUT
SD
mkdir -p $W/fakebin && mv $W/fakebin-sd $W/fakebin/sensors-detect && chmod +x $W/fakebin/sensors-detect
printf '#!/bin/sh\nexit 0\n' > $W/fakebin/update-grub; chmod +x $W/fakebin/update-grub
out=$(PATH=$W/fakebin:$PATH /opt/fankata/bin/fankata-troubleshoot scan)
printf "%s\n" "$out" | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r["ok"] and r["scan"]["chips"][0]["driver"] == "nct6775", r; print("scan ok:", r["scan"]["chips"][0]["chip"])'
PATH=$W/fakebin:$PATH /opt/fankata/bin/fankata-troubleshoot grub-add >/dev/null
grep -q 'acpi_enforce_resources=lax' /etc/default/grub.d/fankata.cfg && echo "grub-add wrote the drop-in"
PATH=$W/fakebin:$PATH /opt/fankata/bin/fankata-troubleshoot grub-remove >/dev/null
test ! -e /etc/default/grub.d/fankata.cfg && echo "grub-remove deleted it"

echo "== fankata-servicectl (turning the service on/off from the app)"
if /opt/fankata/bin/fankata-servicectl bogus 2>/dev/null; then echo "helper accepted a bad argument"; exit 1; fi
mkdir -p $W/fakebin; printf '#!/bin/sh\necho "$@" > %s\n' $W/systemctl.args > $W/fakebin/systemctl; chmod +x $W/fakebin/systemctl
PATH=$W/fakebin:$PATH /opt/fankata/bin/fankata-servicectl disable
[ "$(cat $W/systemctl.args)" = "disable --now fankata.service" ] || { echo "helper ran: $(cat $W/systemctl.args)"; exit 1; }
echo "helper ok: $(cat $W/systemctl.args)"
kill $SIM 2>/dev/null || true

echo "== remove and purge"
apt-get remove -y -qq fankata >/dev/null
test ! -e /usr/bin/fankata
apt-get purge -y -qq fankata >/dev/null
test ! -d /opt/fankata/lib
echo "PASS $PRETTY_NAME"
