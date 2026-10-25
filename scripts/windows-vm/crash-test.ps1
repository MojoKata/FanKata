$svc = Get-CimInstance Win32_Service -Filter "Name='fankatad'"
"before: pid {0}, {1}" -f $svc.ProcessId, $svc.State
$en = "C:\ProgramData\Fankata\sim\sys\devices\platform\nct6775.656\hwmon\hwmon3\pwm2_enable"
"pwm2_enable before: " + (Get-Content $en)
Stop-Process -Id $svc.ProcessId -Force
Start-Sleep -Milliseconds 800
"right after kill: " + (Get-Service fankatad).Status
Start-Sleep 7
$svc = Get-CimInstance Win32_Service -Filter "Name='fankatad'"
"after 8 s: pid {0}, {1}" -f $svc.ProcessId, $svc.State
"pwm2_enable after restart: " + (Get-Content $en)
Get-Content C:\ProgramData\Fankata\log\fankatad.log -Tail 2
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'} -MaxEvents 5 |
  Where-Object { $_.Message -like '*Fankata*' } | Select -First 2 | ForEach-Object { "SCM: " + $_.Message }
