# Windows test VM

> **Current VM (2026-10-01):** the VM is shared with AppKata. It lives in `~/kata-winvm`, and
> its container is `kata-win10`. Start it with `docker start kata-win10`, then run
> `WINVM=~/kata-winvm scripts/test-windows-vm.sh`. Run one project's tests at a time. The
> commands below create a new VM from scratch.

Limited testing of the Windows build in a Windows 10 Enterprise 22H2 *evaluation* VM (build 19045, 90-day licence)
(QEMU/KVM in Docker, [`dockurr/windows`](https://github.com/dockur/windows)). A VM has no
fan controller, so fan control itself runs against the service's simulated hardware
(`HKLM\SOFTWARE\Fankata\Simulate = 1`, set by installing with `/SIMULATE=1`).

Start it (the image downloads the ISO from Microsoft and installs unattended, ~10 min):

```sh
mkdir -p ~/fankata-winvm/{storage,oem}
cp scripts/windows-vm/oem-install.bat ~/fankata-winvm/oem/install.bat     # installs OpenSSH at the end of setup
curl -L -o ~/fankata-winvm/oem/OpenSSH-Win64.zip \
  https://github.com/PowerShell/Win32-OpenSSH/releases/download/10.0.0.0p2-Preview/OpenSSH-Win64.zip
ssh-keygen -t ed25519 -N "" -f ~/fankata-winvm/vm_key && cp ~/fankata-winvm/vm_key.pub ~/fankata-winvm/oem/authorized_key.pub
docker run -d --name fankata-win10 --device /dev/kvm --device /dev/net/tun --cap-add NET_ADMIN \
  -e VERSION=10e -e RAM_SIZE=8G -e CPU_CORES=4 -e DISK_SIZE=64G -e USERNAME=fankata -e PASSWORD=<pick one> \
  -e USER_PORTS=22 -p 127.0.0.1:8006:8006 -p 127.0.0.1:3389:3389 -p 127.0.0.1:2222:22 \
  -v ~/fankata-winvm/storage:/storage -v ~/fankata-winvm/oem:/oem dockurr/windows
```

The download needs `software-static.download.prss.microsoft.com` (about 4.7 GB). For updates
and activation inside the VM, also open Windows Update (`*.update.microsoft.com`,
`*.delivery.mp.microsoft.com`, `*.windowsupdate.com`) and `*.sls.microsoft.com` /
`licensing.mp.microsoft.com`. Avoid the 2021 LTSC evaluation ISO (`VERSION=ltsc10`): its licence
has a fixed expiry date that has passed, so Windows shuts down every hour.

Then `WINVM=~/fankata-winvm scripts/test-windows-vm.sh`. The screen is at http://127.0.0.1:8006
(or RDP to 127.0.0.1:3389). `vmctl.py` (copied into the VM's storage folder) drives the QEMU
monitor, for real-screen captures (`screendump`) and key presses (`sendkey`), which is how the
UAC prompt and the interactive installer were tested. The image turns UAC off; set
`EnableLUA = 1` and reboot to test the real prompt.
