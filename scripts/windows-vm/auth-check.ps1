param([string]$out)
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$elev = (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
$sess = (Get-Process -Id $PID).SessionId
try {
  $p = New-Object System.IO.Pipes.NamedPipeClientStream(".", "fankata", [System.IO.Pipes.PipeDirection]::InOut)
  $p.Connect(3000)
  $w = New-Object System.IO.StreamWriter($p); $w.AutoFlush = $true
  $r = New-Object System.IO.StreamReader($p)
  $w.WriteLine('{"id":1,"cmd":"get_state"}'); $read = ($r.ReadLine() | ConvertFrom-Json).ok
  $w.WriteLine('{"id":2,"cmd":"pulse_start","fan":"nct6798:pwm3"}'); $wr = $r.ReadLine() | ConvertFrom-Json
  $w.WriteLine('{"id":3,"cmd":"pulse_stop"}'); $null = $r.ReadLine()
  $res = "user={0} session={1} elevated={2} read={3} write={4} {5}" -f $id.Name, $sess, $elev, $read, $wr.ok, $wr.error
} catch { $res = "user={0} session={1} error: {2}" -f $id.Name, $sess, $_ }
$res | Out-File -Encoding utf8 $out
