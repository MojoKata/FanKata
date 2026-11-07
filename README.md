# Fankata

Fan control for Linux and Windows. **Curves** turn a **Probe** (a temperature sensor, or an
expression combining several) into a speed for each **Fan**. Everything shown in
the window is applied by a small root service, `fankatad`. It keeps running when
the window is closed, and returns every fan to its firmware default when it
stops.

- Requirements: [`docs/requirements.md`](docs/requirements.md)
- Mockups: [`screenshots/`](screenshots/README.md)
- Release builds: [`releases/`](releases/)

## Install

### Linux

Works on Ubuntu 22.04 or newer, and on Linux Mint 21 or newer (x86_64):

```sh
sudo apt install ./fankata_0.1.0_amd64.deb
```

The package installs the app (menu entry **Fankata**) and enables `fankata.service`.
If no fans show up, click **Troubleshoot** in the Fans view (or **⋮ → Troubleshoot fans…**).
It finds the board's fan chip with `sensors-detect`, loads its driver, and handles
firmware conflicts and Gigabyte's ITE chips; see [Fans missing?](#fans-missing).

Turn fan control off or on from the app's ⋮ menu (**Fan control service**). Off stops the
service, so every fan goes back to firmware/BIOS control, and it stays off across reboots.

Useful commands:

```sh
systemctl status fankata            # service state
journalctl -u fankata -f            # service log
sudo systemctl restart fankata      # re-scan hardware
sudo apt remove fankata             # stops the service; fans return to their defaults
```

The configuration lives in `/etc/fankata/config.toml` and is owned by the service.
Edit it through the app; the service checks every change before saving it.

#### Fans missing?

Fankata lists every **controllable** fan output: a `pwmN` file under `/sys/class/hwmon`.
A fan that has only a speed sensor (`fanN_input`), or whose chip has no Linux driver loaded,
can't be controlled, so it doesn't appear.

**Troubleshoot fans** (in the Fans view when nothing is found, and in the ⋮ menu) checks this for you.
Every step that changes something asks for an administrator password:

- **Install lm-sensors**, if it's missing.
- **Scan** (optional): runs `sensors-detect`, but only its CPU and Super I/O probes. It skips the
  riskier SMBus/ISA probing and writes no configuration.
- **Load driver**: loads the driver the scan names, optionally at every boot
  (`/etc/modules-load.d/fankata.conf`), and restarts the service.
- **Firmware conflicts** (`ACPI ... resource conflict`): reloads `it87` with `ignore_resource_conflict=1`
  where the driver supports it. Otherwise it offers to add `acpi_enforce_resources=lax` as
  `/etc/default/grub.d/fankata.cfg`, showing that file and the boot options before and after
  first. **Remove boot option** undoes it.
- **Gigabyte boards**: recognises their (often two) ITE chips, and shows the community `it87`
  DKMS install steps when the kernel's driver doesn't know the chip, including the Secure Boot key
  prompt.
- ThinkPad fan control, NVIDIA cards, and the Ubuntu 22.04 HWE kernel.

If nothing can be fixed automatically it opens **Things to try**, and **Copy report** gives you a
text report to attach to an issue. To collect the same by hand:

```sh
{ uname -r; cat /sys/class/dmi/id/board_vendor /sys/class/dmi/id/board_name
  for h in /sys/class/hwmon/hwmon*; do
    echo "== $h  $(cat $h/name)  -> $(readlink -f $h)"
    ls $h | grep -E '^(pwm[0-9]+(_enable|_mode)?|fan[0-9]+_(input|label))$' | tr '\n' ' '; echo
  done
  lsmod | grep -iE 'nct67|nct6775|it87|w83|f71882|asus|gigabyte|dell|thinkpad|amdgpu|nouveau|nzxt|corsair'
  sensors
  sudo dmesg | grep -iE 'nct67|it87|hwmon|ACPI.*(resource|conflict)|lpc|smbus'
  journalctl -u fankata -b --no-pager | grep -iE 'fans|probes|error|warn'
} 2>&1 | tee ~/fankata-hw.txt
```

What to look for:

| Finding | Meaning |
|---|---|
| No `nct67xx`/`it87`-style chip at all | The board's fan chip driver isn't loaded. Try `sudo sensors-detect` (from `lm-sensors`) and add the module it suggests. Many ITE chips need the out-of-tree `it87` driver. |
| `ACPI ... resource conflict` in dmesg | The firmware claims the chip. Boot with `acpi_enforce_resources=lax`, or use a board-specific driver such as `asus-ec-sensors` (which reads but doesn't control). |
| `fanN_input` without a matching `pwmN` | The speed is readable but there's no control for it. Typical for NVIDIA cards (no hwmon control), many laptops, and fan headers the driver can't drive. |
| Several fans on one header (splitter or hub) | They share one `pwmN`, so they appear as one fan. |
| An old kernel (`uname -r`) with a new board | The `nct6775` driver learns new chips over time. Ubuntu 22.04's HWE kernel (`linux-generic-hwe-22.04`) helps. |

### Windows 10 (1809+) and 11, x64

Run `Fankata-0.1.0-setup.exe` and accept the UAC prompt. The installer:

- installs the app;
- installs the PawnIO driver if it's missing;
- registers and starts the **Fankata fan control** service.

If fans are missing, **Troubleshoot fans** (⋮ menu, or the button in an empty Fans view)
checks the service, the PawnIO driver (with **Repair**), the Super I/O chips, other fan or RGB
software that's running (Armoury Crate, iCUE, NZXT CAM, Gigabyte Control Center…), laptops, and
Gigabyte BIOS settings.

The builds aren't code-signed yet, so Windows shows "Unknown publisher". Hardware
support comes from LibreHardwareMonitor. The configuration is in
`%ProgramData%\Fankata\config.toml` and the service log is in `%ProgramData%\Fankata\log`.
Uninstall from *Apps & features*: this returns every fan to firmware control and leaves
PawnIO installed.

## Layout

| Path | What |
|---|---|
| `src/fankata_core/` | Shared by GUI and service: PCHIP curves, expression parser, config (TOML), hwmon access |
| `src/fankatad/` | The service: control loop, restore-to-default, Speed pulse. Hardware backends in `backends/` (hwmon, LibreHardwareMonitor, simulated). Transports: Unix socket + polkit (Linux), named pipe + Windows service (`server_win.py`, `winsvc.py`) |
| `src/fankata/` | The PySide6 + QML GUI |
| `tests/` | Unit tests, `gui_drag.py` (real mouse drags), and `fakesysfs.py` (a simulated hwmon tree; the model is in `fankatad/simulate.py`) |
| `packaging/` | Linux: systemd unit, polkit policy, root helpers (`fankata-servicectl`, `fankata-troubleshoot`), desktop entry, icons, Debian control files. `packaging/windows/`: PyInstaller spec, Inno Setup script, `.ico`, third-party notices |
| `scripts/` | `build-deb.sh`, `test-deb.sh`, `build-windows.sh`, `test-windows-vm.sh` (+ `windows-vm/`), `demo.sh` |
| `screenshots/src/` | Mockup generator, plus `export-assets.js` which exports the app's artwork from it |

## Develop

```sh
python3 -m unittest discover -s tests          # needs tomli on Python 3.10
python3 -m venv .venv && .venv/bin/pip install PySide6-Essentials==6.9.3 tomli
PYTHON=.venv/bin/python scripts/demo.sh        # simulated hardware, no root needed
PYTHON=.venv/bin/python scripts/demo.sh --tour /tmp/shots --theme dark   # screenshot every screen
.venv/bin/python tests/gui_drag.py              # real mouse drags on the Fans view (offscreen)
.venv/bin/python tests/gui_service.py           # turning the service off and on from the app
.venv/bin/python tests/gui_troubleshoot.py      # Troubleshoot fans: scan, load a driver, the boot-option confirmation
```

## Release build

```sh
make            # = make deb windows zip; everything lands in releases/
```

| Target | Output in `releases/` |
|---|---|
| `make deb` | `fankata_<ver>_amd64.deb` + `.sha256` (runs the unit tests first) |
| `make windows` | `Fankata-<ver>-setup.exe` + `.sha256` |
| `make zip` | `source.zip`: every file in the repo except what `.gitignore` excludes (build outputs, `releases/`, Python caches) |
| `make test` / `make test-deb` / `make test-windows` | unit tests / install tests on Ubuntu and Mint / install tests in the shared Windows VM (needs KVM) |

`source.zip` holds everything needed to rebuild: unpack it and `make deb windows` produces both packages.

## Build and test the package

Needs Docker:

```sh
scripts/build-deb.sh    # builds in ubuntu:22.04; writes releases/fankata_<ver>_amd64.deb + .sha256
scripts/test-deb.sh     # installs it on Ubuntu 22.04/24.04 and Linux Mint 21/22, smoke-tests it,
                        # and screenshots the installed app on Ubuntu 22.04
```

The artwork in `src/fankata/qml/assets/art/` and `packaging/icons/` is generated from the mockup code:
`NODE_PATH=<dir containing @resvg/resvg-js> node screenshots/src/export-assets.js`.

## Build and test for Windows (on Linux)

Needs Docker:

```sh
scripts/build-windows.sh                 # PyInstaller + Inno Setup under Wine → releases/Fankata-<ver>-setup.exe + .sha256
scripts/test-windows-vm.sh               # install and check in the shared Windows 10 test VM; saves screenshots/windows/
```

`scripts/windows-vm/README.md` explains how the tests use the machine's shared Windows 10 22H2 VM
(QEMU/KVM in Docker), which projects share through the [coworker protocol](https://github.com/MojoKata/coworker).

## Repository settings

`scripts/repo-admin.sh check` reads this repository's GitHub settings back (exit 1 when one differs); `scripts/repo-admin.sh
apply`, run by an admin with `gh` logged in, sets them: a ruleset on `master` (a pull request to
merge, squash only, no force push or deletion), squash merging only with the branch deleted once merged, the Actions token
read-only, actions pinned by SHA, fork pull requests' runs approved first, and private vulnerability
reporting. Each MojoKata repository has the same script; only its settings block differs.
