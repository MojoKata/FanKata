# Windows test VM

Fankata's install tests for the Windows build run in the machine's shared Windows 10 VM: `win10`
in `$COWORKER_HOME/vms` (`~/coworker/vms` unless `COWORKER_HOME` says otherwise). The VM is
described once, in its own folder (`~/coworker/vms/win10/README.md`, with `vm.env` saying how to
reach it), and used through the [coworker protocol](https://github.com/MojoKata/coworker), whose
commands are installed in `~/coworker/bin` by that repository's `install.sh`. Fankata claims the VM,
and `scripts/test-windows-vm.sh` holds its lock (`vms lock`) from the first command to the last
file copied back, so a run of another project waits for this one (and this one for theirs). The
script starts the VM's container if it isn't running and then stops it when the run ends, pass or
fail; `--keep-vm` leaves it running, for runs back to back, and a VM that was already running is
left running.

## What Fankata claims, and why

- **The VM `win10`** (`~/coworker/vms/win10.fankata`): the install tests of
  `Fankata-<ver>-setup.exe`: the service and the PawnIO driver, the pipe protocol on real
  LibreHardwareMonitor and on simulated hardware, a crash restart, turning the service off and on as
  the signed-in user, and the screenshot tour in `screenshots/windows/{dark,light}`.
- **The ISO `win10x64.iso`** (`win10x64.iso.fankata` in `~/coworker/downloads`): what the VM is
  built from. It stays while a project claims it, so a rebuild needn't download 5 GB again. The
  `downloads` command fetches, claims, releases and lists it; never download an ISO into this
  repository's folders.

## Running the tests

```sh
scripts/test-windows-vm.sh        # or: make test-windows
scripts/test-windows-vm.sh --keep-vm   # leave the VM running after, for runs back to back
```

A VM has no fan controller, so fan control itself runs against the service's simulated hardware
(`HKLM\SOFTWARE\Fankata\Simulate = 1`, set by installing with `/SIMULATE=1`). The screen is at
http://127.0.0.1:8006 (or RDP to 127.0.0.1:3389) while the container runs. `vmctl.py` (in the VM's
`storage/` folder) drives the QEMU monitor, for real-screen captures (`screendump`) and key presses
(`sendkey`), which is how the UAC prompt and the interactive installer were tested. The image
turns UAC off; set `EnableLUA = 1` and reboot to test the real prompt.

Leave the VM as you found it (the coworker README, "VMs", "Rules"): Fankata's files on Windows go in
`C:\Users\Public\fankata-test` and `C:\shots`, and the tests uninstall what they install. The VM's
account, key, ports and update policy are the machine owner's, in its own `README.md`.

## Rebuilding

How the VM is built, and how to rebuild it, is in `~/coworker/vms/win10/README.md` (`rebuild.sh`);
a rebuild keeps what `vm.env` says, and needs `/dev/kvm`. `oem-install.bat` here is the script the
first VM's `oem/install.bat` was copied from (it installs OpenSSH at the end of setup).

The image downloads its ISO from `software-static.download.prss.microsoft.com` (about 4.7 GB):
fetch it with `~/coworker/bin/downloads fetch` into the shared folder instead, and boot the
container with `-v ~/coworker/downloads/win10x64.iso:/boot.iso` so it doesn't download another. For
updates and activation inside the VM, also open Windows Update (`*.update.microsoft.com`,
`*.delivery.mp.microsoft.com`, `*.windowsupdate.com`) and `*.sls.microsoft.com` /
`licensing.mp.microsoft.com`. Avoid the 2021 LTSC evaluation ISO (`VERSION=ltsc10`): its licence
has a fixed expiry date that has passed, so Windows shuts down every hour.
