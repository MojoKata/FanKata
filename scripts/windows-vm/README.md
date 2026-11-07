# Windows test VM

Fankata's install tests for the Windows build run in the machine's shared Windows 10 VM: `win10`
in `$COWORKER_HOME/vms` (`~/coworker/vms` unless `COWORKER_HOME` says otherwise). The VM is
described once, in its own folder (`~/coworker/vms/win10/README.md`, with `vm.env` saying how to
reach it), and used through the [coworker protocol](https://github.com/MojoKata/coworker), which
Fankata carries as the `coworker/` submodule and calls only through it (`coworker/bin/coworker
status` first, on any machine: it says what's waiting, such as installing coworker). Fankata claims
the VM, under its checkout directory's name (`FanKata`),
and `scripts/test-windows-vm.sh` holds its lock (`vms lock`) from the first command to the last
file copied back, so a run of another project waits for this one (and this one for theirs). The
script starts the VM's container if it isn't running and then stops it when the run ends, pass or
fail; `--keep-vm` leaves it running, for runs back to back, and a VM that was already running is
left running.

## What Fankata claims, and why

- **The VM `win10`** (`~/coworker/vms/win10.FanKata`): the install tests of
  `Fankata-<ver>-setup.exe`: the service and the PawnIO driver, the pipe protocol on real
  LibreHardwareMonitor and on simulated hardware, a crash restart, turning the service off and on as
  the signed-in user, and the screenshot tour in `screenshots/windows/{dark,light}`.
- **The ISO `win10x64.iso`** (`win10x64.iso.FanKata` in `~/coworker/downloads`): what the VM is
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
(`sendkey`), which is how the UAC prompt and the interactive installer were tested: the VM folder's
`shot.sh NAME` saves a capture as `desktop/NAME.png` and `keys.sh` sends keys. `shot.sh` turns QEMU's
PPM into PNG with Pillow (PIL) on purpose: the PNG sizes and quality of the ways to do it were measured,
and Pillow's were the best, so it stays even where it has to be installed (`python3 -m pip install
--user pillow`, or `PYTHON=` a Python that has it). The image turns UAC off; set `EnableLUA = 1` and
reboot to test the real prompt.

Leave the VM as you found it (the coworker README, "VMs", "Rules"): Fankata's files on Windows go in
`C:\Users\Public\fankata-test` and `C:\shots`, and the tests uninstall what they install. The VM's
account, key, ports and update policy are the machine owner's: its recipe in coworker, and its own
`README.md`.

## Rebuilding

The VM is built from its recipe in coworker (`coworker/vms/win10/`, the coworker README, "VM
recipes"): the image, the account, the ports and `oem/install.bat`, which installs OpenSSH and holds
the VM on Windows 10 22H2. `coworker/bin/vms create win10 --yes` rebuilds it (a human's call: it
replaces the VM every project uses; it needs `/dev/kvm`), and `coworker/bin/vms update win10`
brings it up to date with Windows Update. Both reach Microsoft's servers; `coworker/bin/deps hosts`
lists which. A change to how the VM is built is a PR to coworker, not a file here.

Avoid the 2021 LTSC evaluation ISO (`VERSION=ltsc10`): its licence has a fixed expiry date that has
passed, so Windows shuts down every hour.
