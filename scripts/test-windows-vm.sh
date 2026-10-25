#!/bin/sh
# Install the latest Windows build in the test VM (see scripts/windows-vm/README.md)
# and check it: service + PawnIO, the pipe protocol on real LibreHardwareMonitor and on
# simulated hardware, crash restart, and screenshots of every screen into
# screenshots/windows/{dark,light}.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
WINVM=${WINVM:?set WINVM to the VM folder (holding vm_key)}
SETUP=$(ls -t "$HERE"/releases/Fankata-*-setup.exe | head -1)
SSH="ssh -q -i $WINVM/vm_key -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=$WINVM/known_hosts -o BatchMode=yes fankata@127.0.0.1"
SCP="scp -q -i $WINVM/vm_key -P 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=$WINVM/known_hosts -o BatchMode=yes"
D=C:/Users/Public/fankata-test
$SSH "New-Item -ItemType Directory -Force $D | Out-Null"
$SCP "$SETUP" "$HERE"/scripts/windows-vm/*.ps1 "$HERE/scripts/demo/config.toml" "fankata@127.0.0.1:$D/"
S=$(basename "$SETUP")
run() { $SSH "$1" 2>&1 | tr -d '\r' | grep -v '^$' || true; }
installed() {   # fail unless the previous step's installer exited 0
    echo "$1" | grep -q "installer exit: 0" || { echo "$1"; echo "FAIL: installer did not succeed"; exit 1; }
    echo "$1"
}

echo "== install (real hardware path)"
installed "$(run "Remove-ItemProperty HKLM:\\SOFTWARE\\Fankata -Name Simulate -ErrorAction SilentlyContinue
     \$p = Start-Process -Wait -PassThru $D/$S -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'
     'installer exit: ' + \$p.ExitCode; Restart-Service fankatad; Start-Sleep 6
     'service: ' + (Get-Service fankatad).Status + ', start ' + (Get-Service fankatad).StartType
     'PawnIO driver: ' + (Get-Service PawnIO).Status
     powershell -NoProfile -ExecutionPolicy Bypass -File $D/pipe-check.ps1 | Select -First 4")"

echo "== no fan controls (this VM has no fan chip): empty Fans view and Troubleshoot fans"
run "Remove-Item -Recurse -Force C:\\shots -ErrorAction SilentlyContinue
     foreach (\$t in 'dark','light') {
       \$p = Start-Process -Wait -PassThru 'C:\\Program Files\\Fankata\\fankata.exe' -ArgumentList '--tour',\"C:\\shots\\\$t\",'--theme',\$t,'--tour-only','16-fans-empty,19-troubleshoot-tips'
       '{0}: {1}' -f \$t, ((Get-ChildItem C:\\shots\\\$t).Name -join ', ') }"
mkdir -p "$HERE/screenshots/windows/.empty"
$SCP fankata@127.0.0.1:C:/shots/dark/16-fans-empty.png "$HERE/screenshots/windows/.empty/dark-16-fans-empty.png"
$SCP fankata@127.0.0.1:C:/shots/dark/19-troubleshoot-tips.png "$HERE/screenshots/windows/.empty/dark-19-troubleshoot-tips.png"
$SCP fankata@127.0.0.1:C:/shots/light/16-fans-empty.png "$HERE/screenshots/windows/.empty/light-16-fans-empty.png"
$SCP fankata@127.0.0.1:C:/shots/light/19-troubleshoot-tips.png "$HERE/screenshots/windows/.empty/light-19-troubleshoot-tips.png"

echo "== simulated hardware"
installed "$(run "\$p = Start-Process -Wait -PassThru $D/$S -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SIMULATE=1'
     'installer exit: ' + \$p.ExitCode
     Stop-Service fankatad; Copy-Item $D/config.toml C:\\ProgramData\\Fankata\\config.toml -Force
     Start-Service fankatad; Start-Sleep 6
     powershell -NoProfile -ExecutionPolicy Bypass -File $D/pipe-check.ps1 | Select -First 4")"

echo "== crash restart"
run "powershell -NoProfile -ExecutionPolicy Bypass -File $D/crash-test.ps1 | Select-String 'pid|SCM: The'"

echo "== screenshots"
run "Remove-Item -Recurse -Force C:\\shots -ErrorAction SilentlyContinue
     foreach (\$t in 'dark','light') {
       \$p = Start-Process -Wait -PassThru 'C:\\Program Files\\Fankata\\fankata.exe' -ArgumentList '--tour',\"C:\\shots\\\$t\",'--theme',\$t,'--tour-warmup','45'
       '{0}: {1} screens' -f \$t, (Get-ChildItem C:\\shots\\\$t).Count }"
for t in dark light; do rm -rf "$HERE/screenshots/windows/$t"; done
$SCP -r fankata@127.0.0.1:C:/shots/dark fankata@127.0.0.1:C:/shots/light "$HERE/screenshots/windows/"
for t in dark light; do      # the no-fan-chip screens from the real-hardware install
    for n in 16-fans-empty 19-troubleshoot-tips; do mv "$HERE/screenshots/windows/.empty/$t-$n.png" "$HERE/screenshots/windows/$t/$n.png"; done
done
rmdir "$HERE/screenshots/windows/.empty"
echo "saved screenshots/windows/{dark,light}"

echo "== turning the service off and on as the signed-in user (not elevated)"
toggle() {   # run service-toggle.ps1 <mode> in the console session without elevation
    run "Remove-Item $D/toggle-$1.txt -ErrorAction SilentlyContinue
         schtasks /create /tn FankataToggle /tr \"powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $D/service-toggle.ps1 $1 $D/toggle-$1.txt\" /sc once /st 23:59 /ru fankata /it /rl LIMITED /f | Out-Null
         schtasks /run /tn FankataToggle | Out-Null
         for (\$i = 0; \$i -lt 40 -and -not (Test-Path $D/toggle-$1.txt); \$i++) { Start-Sleep 1 }
         schtasks /delete /tn FankataToggle /f | Out-Null
         Get-Content $D/toggle-$1.txt"
}
OFF=$(toggle off); echo "$OFF"
echo "$OFF" | grep -q "status=Stopped start=Manual pwm2_enable=5" || { echo "FAIL: turning off"; exit 1; }
run "foreach (\$t in 'dark','light') {
       \$p = Start-Process -Wait -PassThru 'C:\\Program Files\\Fankata\\fankata.exe' -ArgumentList '--tour',\"C:\\shots\\\$t\",'--theme',\$t,'--tour-only','12-service-off'
       '{0}: 12-service-off {1}' -f \$t, (Test-Path \"C:\\shots\\\$t\\12-service-off.png\") }"
$SCP fankata@127.0.0.1:C:/shots/dark/12-service-off.png "$HERE/screenshots/windows/dark/"
$SCP fankata@127.0.0.1:C:/shots/light/12-service-off.png "$HERE/screenshots/windows/light/"
ON=$(toggle on); echo "$ON"
echo "$ON" | grep -q "status=Running start=Auto" || { echo "FAIL: turning on"; exit 1; }
echo "service on/off ok"
