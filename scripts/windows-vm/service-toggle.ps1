# Turn the Fankata service off, then on, as the calling user (run non-elevated in the
# signed-in session): off goes through the service's pipe ("service_disable", an
# authorized request), on is "sc start" (signed-in users may start this service).
param([string]$mode, [string]$out)
$en = "C:\ProgramData\Fankata\sim\sys\devices\platform\nct6775.656\hwmon\hwmon3\pwm2_enable"
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
$lines = @("user={0} session={1} elevated={2}" -f $id.Name, (Get-Process -Id $PID).SessionId, $elev)
function StartType { (Get-CimInstance Win32_Service -Filter "Name='fankatad'").StartMode }
if ($mode -eq "off") {
  $p = New-Object System.IO.Pipes.NamedPipeClientStream(".", "fankata", [System.IO.Pipes.PipeDirection]::InOut)
  $p.Connect(3000)
  $w = New-Object System.IO.StreamWriter($p); $w.AutoFlush = $true
  $r = New-Object System.IO.StreamReader($p)
  $w.WriteLine('{"id":1,"cmd":"service_disable"}'); $reply = $r.ReadLine() | ConvertFrom-Json
  $p.Dispose()
  $lines += "service_disable ok=" + $reply.ok + " " + $reply.error
  (Get-Service fankatad).WaitForStatus("Stopped", "00:00:20")
  $lines += "after off: status=" + (Get-Service fankatad).Status + " start=" + (StartType) + " pwm2_enable=" + (Get-Content $en)
} else {
  $o = & sc.exe start fankatad 2>&1; $code = $LASTEXITCODE
  $lines += "sc start exit=" + $code
  (Get-Service fankatad).WaitForStatus("Running", "00:00:20")
  Start-Sleep 4
  $lines += "after on: status=" + (Get-Service fankatad).Status + " start=" + (StartType) + " pwm2_enable=" + (Get-Content $en)
}
$lines | Out-File -Encoding utf8 $out
