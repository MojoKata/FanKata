@echo off
rem Runs once at the end of unattended Windows setup (dockurr/windows OEM hook).
rem Installs OpenSSH Server so the host can drive tests, with PowerShell as the shell.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -Force C:\OEM\OpenSSH-Win64.zip -DestinationPath 'C:\Program Files';" ^
  "& 'C:\Program Files\OpenSSH-Win64\install-sshd.ps1';" ^
  "New-Item -ItemType Directory -Force C:\ProgramData\ssh | Out-Null;" ^
  "Copy-Item C:\OEM\authorized_key.pub C:\ProgramData\ssh\administrators_authorized_keys -Force;" ^
  "icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F';" ^
  "New-ItemProperty -Path HKLM:\SOFTWARE\OpenSSH -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force;" ^
  "Set-Service sshd -StartupType Automatic; Start-Service sshd;" ^
  "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22"
