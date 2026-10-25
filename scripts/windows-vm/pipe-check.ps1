$p = New-Object System.IO.Pipes.NamedPipeClientStream(".", "fankata", [System.IO.Pipes.PipeDirection]::InOut)
$p.Connect(3000)
$w = New-Object System.IO.StreamWriter($p); $w.AutoFlush = $true
$r = New-Object System.IO.StreamReader($p)
$w.WriteLine('{"id":1,"cmd":"hello","version":1}'); $hello = $r.ReadLine() | ConvertFrom-Json
$w.WriteLine('{"id":2,"cmd":"get_state"}'); $st = ($r.ReadLine() | ConvertFrom-Json).result
"hello: compatible=" + $hello.result.compatible + " service=" + $hello.result.service_version
"hardware: " + $st.service.hardware
"fans: " + $st.fans.Count
$w.WriteLine('{"id":3,"cmd":"diagnose"}'); $dg = ($r.ReadLine() | ConvertFrom-Json).result
"diagnose: PawnIO {0} {1}, {2} chips, Super I/O [{3}], software [{4}], laptop {5}, {6}" -f $dg.pawnio.state, $dg.pawnio.version, $dg.chips.Count, (($dg.chips | Where-Object { $_.kind -eq 'superio' } | ForEach-Object { $_.name }) -join ', '), ($dg.software -join ', '), $dg.laptop, $dg.os
$st.probes | ForEach-Object { "probe {0} = {1} ({2})" -f $_.name, $_.value, $_.desc }
$p.Dispose()
