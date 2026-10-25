# Fankata — Requirements

Fankata is a GUI fan control program for Linux and Windows. It links **Probes** (temperature
sources) to **Fans** (PWM-controlled devices) through **Curves** (temperature →
duty-cycle mappings).

This document describes the current desired behavior of the application. It is
not a changelog. Mockups live in [`../screenshots`](../screenshots/README.md).

---

## 1. Platform and architecture

1.1. The program must run on Ubuntu 22.04 LTS and newer, and on Windows 10
(version 1809 or later) and Windows 11, x64. Sections 1.2–1.8 describe Linux;
Windows differences are in 1.12.

1.2. Fan and temperature access uses the kernel `hwmon` sysfs interface
(`/sys/class/hwmon/*`: `tempN_input`, `fanN_input`, `pwmN`, `pwmN_enable`).

1.3. Everything is written in Python 3.10 or newer. The GUI uses PySide6
(Qt 6 with QML).

1.4. Fankata runs as two processes:

- **`fankata`**, the GUI, runs as the desktop user.
- **`fankatad`**, the service, runs as root under systemd (`fankata.service`). It
  performs every hardware write and keeps applying assigned Curves while the
  GUI is closed. It runs on the system `python3` in isolated mode and uses
  only the Python standard library, plus a vendored copy of `tomli` for
  reading TOML on Python 3.10.

1.5. Curve evaluation and expression parsing live in one shared pure-Python
package used by both processes, so the GUI's drawing and the service's control
always agree.

1.6. Fankata is distributed as a single `.deb` package. It installs:

- The GUI, with PySide6 (PySide6-Essentials) bundled under
  `/opt/fankata/vendor`, so it works with any system `python3` from 3.10 on.
  It is launched from the app menu or as `fankata`.
- The service, its systemd unit and its polkit policy.
- Two root helpers run through `pkexec`: `fankata-servicectl` (4.6) and
  `fankata-troubleshoot` (4.7.3).
- A desktop entry and the app icon.

Installing the package enables and starts the service. Removing it stops the
service, which returns every Fan to its default state (8.3). Purging it also
deletes `/etc/fankata`.

1.6.1. The package targets x86_64 (amd64) Ubuntu 22.04 and 24.04 and Linux
Mint 21 and 22. Every release is tested by installing it on each of these.

1.7. The GUI and service communicate over a Unix domain socket,
`/run/fankata/fankata.sock`, carrying newline-delimited JSON messages. The first
exchange is a versioned handshake.

1.8. Any local user may connect and read state. Every change requires the
polkit action `org.fankata.control`. The service checks the caller's process
(from the socket's peer credentials) with polkit. Users in an active local
session are allowed without a password; others are asked to authenticate.
Turning the service on or off (4.6) uses a second polkit action,
`org.fankata.service`, with the same rule. It authorizes one helper,
`/opt/fankata/bin/fankata-servicectl enable|disable`, run through `pkexec`,
which calls `systemctl enable --now` or `systemctl disable --now` for
`fankata.service` only. Troubleshoot fans (4.7.3) uses a third action,
`org.fankata.troubleshoot`, which always asks for an administrator password
(cached for a few minutes). It authorizes `/opt/fankata/bin/fankata-troubleshoot`,
which accepts only its fixed subcommands.

1.9. The service validates every change itself (Curve rules, Allow zero
floor, Probe cycles) and never trusts the GUI's validation.

1.10. If the service cannot be reached (it is off, 4.6, or it failed), the
GUI runs in read-only monitoring mode. On Linux, Fans and Probes still show
live values read directly from sysfs, with each Fan's saved Curve and Probe
grouping, and every Fan shows "System default". Editing is disabled. A banner
reads "Fan control is off: fans are under firmware control, and Fankata is
showing live readings only." and has a **Turn on** button (4.6). On Windows,
readings need the service's driver, so the banner only says that fan control
is off.

1.11. The GUI follows the desktop light/dark preference (on Windows, the
"app mode" setting). Dark is the primary design target; light must be equally
complete.

1.12. Windows

1.12.1. **Hardware access.** LibreHardwareMonitorLib, loaded through pythonnet
on the .NET Framework 4.8 that ships with Windows, over the PawnIO driver.
LibreHardwareMonitor's controllable fan outputs become Fans, and its fan speed
sensors are paired with them by index. Its temperature sensors become system
Probes named as in 7.3.2, with the same aliases (7.3.3). Board support is
whatever LibreHardwareMonitor supports.

1.12.2. **Service.** `fankatad` is a Windows service ("Fankata fan control")
running as LocalSystem with automatic start. Its recovery actions restart it
2, 5 and 10 seconds after a failure.

1.12.3. **GUI ↔ service.** A named pipe, `\\.\pipe\fankata`, carries the same
protocol as 1.7. It accepts local connections only.

1.12.4. **Who may change settings** (instead of polkit, 1.8). Anyone signed in
may connect and read state. Changes are allowed for users in an active
interactive session at the PC (console or Remote Desktop) and for elevated
administrators. Anyone else is refused with "Only someone signed in at this
PC, or an administrator, can change fan control."

1.12.5. **Distribution.** A single `Fankata-<version>-setup.exe` (Inno
Setup). It asks for elevation once (UAC) and then:

- installs the app to `Program Files\Fankata`, including `THIRD-PARTY.txt`
  with the bundled components' licences;
- runs the official, signed PawnIO installer silently if PawnIO isn't
  installed yet, and keeps a copy in `Program Files\Fankata\pawnio` for
  Troubleshoot fans → **Repair** (4.7.4);
- registers and starts the service;
- adds a Start Menu entry and an Apps & features entry.

An upgrade closes any open Fankata window and stops the service before
replacing files. Uninstalling stops the service, which returns every Fan to its
default state, and removes the service and program files. It keeps the
configuration and leaves PawnIO installed, because other tools use it.

1.12.6. **Locations.** Configuration: `%ProgramData%\Fankata\config.toml`.
Service state: `%ProgramData%\Fankata\run`; files older than the last boot are
discarded, like `/run` on Linux. Log: `%ProgramData%\Fankata\log`. GUI view
preferences: `%APPDATA%\Fankata`.

1.12.7. **Returning to default** uses LibreHardwareMonitor's `SetDefault`,
which hands the output back to firmware control. The detail panel therefore
always shows "Automatic (firmware control)" (5.4.6).

1.12.8. **Fail-safe** (instead of 8.4). There is no equivalent of
`ExecStopPost`. When the service stops, or Windows shuts down, it restores
every Fan. If the service crashes, Fans hold their last speed until the
recovery action restarts it about 2 seconds later, and it then resumes
control.

1.12.9. If the driver or LibreHardwareMonitorLib can't be loaded, the service
runs with no Fans. The Fans view then offers Troubleshoot fans (5.1.1), which
says why (for example "Hardware access unavailable … Reinstall Fankata to
install the PawnIO driver") and offers **Repair**.

1.12.10. **Developer option.** `HKLM\SOFTWARE\Fankata\Simulate = 1`, set by
installing with `/SIMULATE=1`, runs the service against simulated hardware
(the same model as the Linux tests). It exists for testing in virtual
machines, which have no fan controller.

1.12.11. **Build and test.** The installer is built on Linux: PyInstaller,
then Inno Setup, both under Wine. Every release is tested in a Windows 10 VM:
install, the UAC prompt, service start at boot, the pipe protocol on
LibreHardwareMonitor and on simulated hardware, who may change settings,
crash restart, turning the service off and on as a non-elevated user, the
`diagnose` command and the troubleshooter's screens, upgrade and uninstall.

1.12.12. **Turning the service off and on (4.6) on Windows.**

- **Off:** the app sends `service_disable` over the pipe, authorized as in
  1.12.4. The service sets its own start type to manual, replies, and stops,
  restoring every Fan.
- **On:** the app runs `sc start fankatad`. The installer gives interactive
  (signed-in) users the right to *start* this service, and only that: stopping
  or reconfiguring it remains reserved for administrators and the service
  itself. Whenever the service starts, it sets its start type back to
  automatic.

## 2. Identity

2.1. The application is named **Fankata**.

2.2. The app icon is a four-bladed ninja shuriken with hooked blades and a
center hole, in brushed-steel greys on a charcoal rounded-square tile. It uses
no rainbow or multi-hue colors.

## 3. Concepts

3.1. The program manages three catalogs: **Curves**, **Probes** and **Fans**.

3.2. A Fan is connected to a Probe through a Curve: every update tick, the
Probe's value is used as the Curve's x value, and the resulting y value is the
Fan's duty cycle.

## 4. Views

4.1. The main window has two views, selected from a switcher in the header bar:

- **Fans** (the default view, shown on launch).
- **Curves**, with the **Probes** catalog in a collapsible side panel.

4.2. The design goal is a visually delightful, simple interface: generous
spacing, soft cards, clear typography, and live values that update smoothly
rather than jumping.

4.3. The window draws its own header bar instead of a system title bar. Drag
the header to move the window; double-click it to maximize or restore. The
window edges resize it. The header holds the app icon and name, the view
switcher, an app menu (⋮) and a close button.

4.4. The app menu offers, in order: **Fan control service** (4.6),
**Troubleshoot fans…** (4.7), the theme (Match system, Dark, Light), About
Fankata, and Quit. The theme choice is
remembered (9.2).

4.5. Errors from rejected changes are shown in a short-lived message at the
bottom of the window.

4.6. **Turning fan control off and on.** The first item of the app menu is a
checkbox item, **Fan control service**. Its subtext reads "On · fans follow
their curves" or "Off · fans under firmware control", and "Turning off…" or
"Turning on…" while the change is in progress.

- **Off** stops the service, which returns every Fan to its default state
  (8.3): firmware/BIOS control, or whatever it was before Fankata took
  over. The service stays off across reboots until it is turned on again.
  The app then switches to read-only mode (1.10).
- **On** starts the service and makes it start at boot again. Fans
  immediately follow their Curves again.
- Who may do this follows the same rule as other changes (1.8, 1.12.4):
  users signed in at the PC need no password.
- When the change completes, the app confirms it in a short message, for
  example "Fan control is off. Every fan is back under firmware control."
  If it fails, or takes longer than 30 seconds, the message says so.

4.7. **Troubleshoot fans.** A dialog that finds out why fans are missing and
fixes what it can (on Linux) or points to the fix (on Windows). It opens from
the app menu (4.4) and from the **Troubleshoot** button in an empty Fans view
(5.1.1).

4.7.1. **Layout**, top to bottom:

- The title, with one line saying what it does.
- A summary strip: the number of fan controls found (and on which chips), the
  number of fans that report speed only, and the board with the kernel and
  OS (Linux) or the OS (Windows).
- **Checks**: one row per finding. Each row has a status (ok, warning, failed,
  information, or waiting), a title and a one- or two-line explanation, and
  may have an action button, a checkbox, or a command block with **Copy**.
  Actions that need an administrator show a lock on their button.
- **Things to try** (4.7.5), collapsed by default.
- **Copy report**, **Run again** and **Close**.

4.7.2. The checks are collected again when the dialog opens, on **Run again**,
after every action, and when the service connects or disconnects. Collecting
them never changes anything. While an action runs, its button reads
"Scanning…" or "Working…" and the other actions are disabled. A failed or
cancelled action is reported in the dialog and in a short message.

4.7.3. **Linux.** What the app reads itself, without a password: the sensor
chips and which of them can control a fan, fans that report speed only, the
loaded drivers, the board (DMI), the kernel and OS, Secure Boot, NVIDIA cards,
ThinkPad fan control, the GRUB boot options, and this boot's kernel messages
when the journal allows it. Steps that need root run
`fankata-troubleshoot` through `pkexec` (1.8):

- **Install lm-sensors** (when missing): installs the package with apt.
- **Find the board's fan chip** (optional): runs `sensors-detect`, answering
  yes only to the CPU and Super I/O scans and no to everything else (IPMI, ISA,
  SMBus, writing any configuration). It reads the drivers and chips from the
  summary, plus chips sensors-detect doesn't know (named from their ID, for
  example "ITE IT8688E").
- **Load the driver** the scan names, when it is installed but not loaded. A
  checkbox (on by default) also loads it at every boot by adding it to
  `/etc/modules-load.d/fankata.conf`. Loading restarts the service so the new
  fans appear.
- **The firmware won't share the chip**: when the kernel reports an ACPI
  resource conflict for the fan driver. If the driver has an
  `ignore_resource_conflict` option (`it87` does), the fix is to reload it with
  that option, kept in `/etc/modprobe.d/fankata.conf` when "at every boot" is
  checked. Otherwise the fix is **Add boot option…**: the kernel option
  `acpi_enforce_resources=lax`, written as one new file,
  `/etc/default/grub.d/fankata.cfg`, followed by `update-grub`. Before
  writing, a confirmation shows that file and the resulting kernel boot
  options, each before and after, with the added option highlighted, a
  warning about what the option does, and **Copy commands instead**. Once the
  file exists, a row says to restart (or that the option is active) and
  offers **Remove boot option…**, confirmed the same way.
- **Gigabyte boards** (board vendor Gigabyte): a row explaining that they use
  ITE chips, often two (IT8686E, IT8688E, IT8689E or IT8696E for most
  headers, plus IT8792E or IT87952E for the rest), that `gigabyte_wmi` only
  reads temperatures, and that `it87` should be loaded with
  `ignore_resource_conflict=1` rather than a boot option. When the kernel's
  `it87` can't drive the chip, the dialog shows the steps to install the
  community `it87` driver with DKMS, to copy and run; it never builds or
  installs third-party drivers itself. With Secure Boot on, a row explains
  the signing key and the MOK screen at the next restart.
- **ThinkPad** with fan control off: reload `thinkpad_acpi` with
  `fan_control=1`.
- **NVIDIA cards**: their fans can't be controlled through hwmon.
- **Ubuntu 22.04 on a 5.x kernel** with no fan control: the HWE kernel
  command, to copy.

4.7.4. **Windows.** The service collects the facts (the `diagnose` command,
readable without authorization); while the service is off, the app collects
what it can itself. Checks: the service (with **Turn on**), hardware access,
the PawnIO driver (installed, running, version, and any event-log entries
about Windows blocking it, with **Repair**, which runs the bundled PawnIO
installer through UAC), each Super I/O chip with its number of controls and
the headers that report speed only (by label), other fan or RGB software that
is running (Armoury Crate, iCUE, NZXT CAM, MSI Center, Gigabyte Control
Center, SIV, EasyTune, RGB Fusion, SignalRGB, FanControl, HWiNFO, SpeedFan,
Argus Monitor, AIDA64) with what it interferes with and **Open Task Manager**,
and laptops (a battery is present). Fankata never closes other software. On
Gigabyte boards a row describes the Smart Fan 5/6 BIOS settings (Fan Control
Mode PWM for 4-pin fans, Voltage for 3-pin; not Full Speed). Simulated
hardware (1.12.10) is reported as such.

4.7.5. **Things to try** is a list of suggestions for the platform, kept as
Markdown in the app (`tips/linux.md`, `tips/windows.md`) and rendered as
formatted text: bullets, bold, italic, inline code, links (opened in the
browser) and command blocks with **Copy**. Its header shows how many
suggestions there are. It opens by itself when nothing actionable is left:
after a scan with nothing more to fix (Linux), or when there is nothing more
to check (Windows), with the note "nothing more could be fixed (checked)
automatically".

4.7.6. **Copy report** copies a plain-text report to the clipboard: the
summary, every check, the facts they came from, and the raw output of the
last scan and driver load, for attaching to an issue.

## 5. Fans

5.1. The Fans catalog lists all PWM/fan devices detected on the system.

5.1.1. When no fan controls are found, the Fans view shows a card instead:
an illustration, "No controllable fans found", one line on what was found
(for example the chips that report temperatures only) and a **Troubleshoot**
button that opens Troubleshoot fans (4.7).

5.2. Fans are the primary view. Each detected Fan is shown as a card with:

5.2.1. An illustration of the device, chosen by its best-determined type. Each
type has a distinct illustration:

- Case/radiator fan
- AIO cooler fan
- Pump
- Unknown/generic PWM header

5.2.2. The Fan's name. It defaults to the driver label (for example
`nct6798 · fan2`). The user can rename it.

5.2.3. The current speed, when it can be known:

- RPM, from `fanN_input`.
- Duty cycle %, from `pwmN`, shown as a speed ring that fills clockwise
  from 12 o'clock. The ring's colour follows its position on the dial, like
  a tachometer: green from 0 %, yellow by 45 %, orange by 70 % and red from
  90 % (the "red line"). A ring therefore only shows red when the fan is near
  full speed. Unmanaged fans use the same colours, softened. The bands are
  Calm (0–45 %), Working (45–70 %), Busy (70–90 %) and Red line (90–100 %).
- The illustration's rotor (the pump's light ring for pumps) spins at a rate
  that follows the current speed, easing between readings.
- If the speed cannot be read, the card shows "Speed unknown" instead of a
  number.

5.2.4. Whether the Fan is managed by the app:

- **Managed** fans show the assigned Curve name with a small curve
  thumbnail. They have no "Managed" badge: the Probe group the card sits in
  (5.3) already shows that the Fan is managed, and by which Probe.
- **Unmanaged** fans show a "System default" badge and are visually quieter.
- A card shows a badge only for a state its group doesn't convey: System
  default, Speed pulse (5.5), Returning to system default… (5.4.2), or
  Attention (a warning such as a Probe that can't be read). The detail panel
  follows the same rule (5.4.8).

5.2.5. **Tile size.** Tiles are laid out like a CSS flex row with `flex: 1` and
`max-width: 33%`. Up to three tiles share a row equally, and a narrower window
holds fewer tiles per row. A tile is designed at 380 × 290 px and scales with
its width, keeping that aspect ratio. Everything inside it scales the same way:
text, illustration, speed ring, badges, the curve thumbnail and line widths. The
smallest tile is 360 px wide (fewer tiles per row below that) and the largest is
2× (760 × 580 px). In wider windows the row keeps three 2× tiles and leaves
the rest empty.

5.3. Grouping by Probe

5.3.1. Fan cards are grouped by their Probe. Each group starts with a header
showing the Probe as a pill: a thermometer, the Probe name, and its current
value. After the pill come the Probe's description (the sensor, or a custom
Probe's expression) and the number of Fans in the group.

5.3.1.1. The pill's thermometer fills up to 100 °C in four 25 °C steps. Its
colour, and the colour of the temperature text next to it, follow the step:

| Temperature | Colour | Thermometer |
|---|---|---|
| 25 °C or below | blue | only the bulb filled |
| above 25 to 50 °C | yellow | bulb and one third of the stem |
| above 50 to 75 °C | orange | bulb and two thirds of the stem |
| above 75 °C | red | full |

The light theme uses deeper shades of the same four colours, so the text
stays readable. The thermometer is drawn on whole pixels: the tube, the column
and the bulb share one centre line, and the column keeps a 1 px gap to each
wall of the tube. When the value can't be read, the thermometer is grey with
only the bulb filled, and the text shows "—".

5.3.2. Fans without both a Curve and a Probe form the last group, **Unmanaged
fans**. Its header pill reads "Unmanaged fans".

5.3.3. Groups appear in Probe catalog order: the system aliases first, then
other system sensors, then custom Probes, with Unmanaged fans last. Only
groups that contain Fans are shown.

5.3.4. Within a group, cards run left to right, then top to bottom. By
default they are sorted alphabetically by name. Once the user reorders them
(5.3.6), that order is kept (9.2). Fans that are new since then are placed
after the ordered ones, alphabetically.

5.3.5. When a Fan's Probe changes, for example from the detail panel, its card
animates from its old place to its place in the new group. The other cards
animate to close the gap and make room.

5.3.6. Cards can be dragged. The dragged card lifts, tilts slightly and
follows the pointer. The cards of the group under it move aside to show a
highlighted slot where it will land. Dropping it within its own group
reorders the group.

5.3.7. While a card is dragged over a different group, that group's Probe pill
lights up (accent colour and glow), and the header says what dropping will do.

5.3.8. Dropping a card into a different group:

- A **managed** Fan takes that group's Probe and keeps its Curve.
- An **unmanaged** Fan takes that group's Probe and the Curve of the Fan in
  that group nearest to the drop point. The hint names that Fan and Curve.
- Dropping into **Unmanaged fans** returns the Fan to its default state (8.3).

5.3.9. During a drag, the Unmanaged fans group is always shown as a drop
target, and the group the card came from stays visible even if it is now
empty. Dragging near the top or bottom edge scrolls the view.

5.3.10. A click without movement selects the card, as before. Dragging is
disabled in read-only mode (1.10).

5.3.11. The Fans view header shows a summary, such as "6 detected · 4 managed
by Fankata", and filter chips: All, Managed (hides Unmanaged fans), Unmanaged
(shows only Unmanaged fans).

5.4. Selecting a Fan card opens its detail panel, which contains:

5.4.1. A **Curve** select field that picks from the Curve catalog.

5.4.2. The Curve field can be cleared. Clearing it returns the Fan device to
its default state (8.3). While the service does this, the card shows
"Returning to system default…". It then shows "System default" once the
service confirms the restore, or a warning if the device could only be
partially restored.

5.4.3. A **Probe** select field that picks from the Probe catalog. It is shown
and required when the Fan has a Curve. When a Curve is chosen for a Fan that
has no Probe yet, the Probe defaults to `sys.coolant` for AIO fans and pumps
(when present) and to `sys.cpu` otherwise.

5.4.4. When both are set, a live chart of the assigned Curve with a marker at
the current operating point (current Probe value, resulting duty cycle).

5.4.5. A Fan with a Curve but no Probe is shown with a warning and is not
controlled until a Probe is chosen.

5.4.6. The detail panel states how the Fan returns to its default when it is
unmanaged: "Automatic (firmware control)", "Fixed at N %", or, for devices
whose original speed can't be read, "Full speed".

5.4.7. The panel header has a vertical ellipsis (⋮) menu button immediately
to the left of its close button. Clicking it opens a menu of device actions.
The menu currently contains one item, **Speed pulse (8 sec)** (5.5), with
the sub-text "Spot this fan by ramping its speed".

5.4.8. The panel shows no "Managed" badge. Like a card (5.2.4), it shows a
badge only for System default, Speed pulse, Returning to system default… or
Attention.

5.5. Speed pulse

5.5.1. **Speed pulse** helps the user find which physical fan a Fan card
represents. It switches the Fan between full speed and a low speed in a steady
rhythm, which is easy to hear, see and feel, even for fans hidden behind
radiators or shrouds.

5.5.2. The pattern is 1 s at 100 %, then 1 s at the low speed, repeated for
8 s. The low speed is 30 % for fans. For pumps it is the pump's current speed,
so a pump is never slowed below where it already is. Speed pulse never stops a
device.

5.5.3. While a pulse runs:

- The Fan's card and the detail panel show a "Speed pulse" badge in place of
  Managed / System default, with ripples around the illustration.
- The illustration's spin speeds up and slows down in step with the physical
  pulses, so the user can match the rhythm on screen to what they hear.
- The detail panel replaces the live curve chart with a pulse chart. It shows
  the commanded duty (a square wave), the measured RPM, the time remaining,
  and a **Stop** button.
- Speed values on the card and panel update live.
- The Curve and Probe fields are disabled.

5.5.4. When the pulse ends (finishes, is stopped, or is aborted), the panel
shows the result of the wiring check (8.7.4) until the user dismisses it.

5.5.5. Only one Speed pulse runs at a time. Starting one while another is
running stops the first.

5.6. Fan type detection uses, in order:

1. The channel label: text containing "pump" means Pump.
2. The hwmon driver: known AIO drivers (`nzxt-kraken2`, `nzxt-kraken3`,
   `asus_rog_ryujin`, `aquacomputer_d5next`), or a label containing "aio" or
   "cpu_opt", means AIO cooler fan.
3. A PWM channel with no matching speed sensor means Generic PWM header.
4. Otherwise, Case fan.

The user can override the detected type from the detail panel.

## 6. Curves

6.1. The program provides a visual catalog of Curves.

6.2. Axes:

6.2.1. The x-axis is a number, typically 0 to 100, typically a temperature in
degrees Celsius.

6.2.2. The y-axis is a number from 0 to 100 %.

6.3. A Curve definition is a name, an **Allow zero** flag, and a set of (x, y)
points.

6.3.1. Curve names must be unique.

6.3.2. Points are always presented in order of increasing x value.

6.3.3. The x values must be unique.

6.3.4. The y values must not decrease as x increases.

6.3.5. A Curve has at least two points.

6.3.6. **Allow zero** is off by default. While it is off, every y value must
be ≥ 20 %. Only when it is on may y values be below 20 % (down to 0 %).

6.4. Rendering:

6.4.1. Curves are presented as attractively styled X/Y graphs.

6.4.2. The points are drawn as small circle markers, connected by a smoothed
line.

6.4.3. The line is tinted along the x-axis from cool (blue) to hot (red) so
the temperature range reads at a glance.

6.4.4. While Allow zero is off, the editor graph shows the region below 20 %
as a hatched "Minimum 20 %" band.

6.5. Evaluation:

6.5.1. The smoothed line is not cosmetic: it is the function used to compute y
for any given x. The drawn line and the computed value must always agree.

6.5.2. Smoothing uses monotone cubic interpolation (Fritsch–Carlson / PCHIP),
so the line passes through every point, never overshoots, and never decreases
between points.

6.5.3. For x below the first point, y equals the first point's y. For x above
the last point, y equals the last point's y.

6.6. The Curves view shows:

- A gallery of Curve cards, each with a thumbnail graph, the name, the point
  count and the number of Fans using it.
- A large editor for the selected Curve. It shows a live marker for each Fan
  using the Curve, at that Fan's current Probe value.

6.7. Editing points on the graph:

6.7.1. Clicking a point removes it. Hovering a point highlights it in the
danger color with a "Click to remove" hint. A Curve that has only two points
does not remove a point on click.

6.7.2. Clicking an empty spot on the graph adds a point at that (x, y) if the
y value is valid: ≥ the y of the previous point, ≤ the y of the next point,
and ≥ 20 % unless Allow zero is on. The x value must not equal an existing
point's x.

6.7.3. While hovering empty space, the graph shows a ghost point with a
"Click to add" hint and a band marking the valid y range at that x. If the
spot is not valid, the ghost is shown in the danger color with the reason,
and clicking does nothing.

6.7.4. Added points snap to whole numbers.

6.8. Editing points in the table:

6.8.1. The points are also listed in an editable table (x, y), always sorted
by x.

6.8.2. Values typed into the table that break a rule (6.3.3, 6.3.4, 6.3.6)
are highlighted with an explanation and are not applied.

6.9. Curve actions:

6.9.1. The editor header has an ellipsis (⋯) menu button at the top right.

6.9.2. The ellipsis menu contains, in order:

- **Duplicate curve**: creates a copy named "<name> copy" and selects it.
- **Allow zero**: a checkbox item, unchecked by default (see 6.3.6).
- **Delete curve**: deletes the Curve. It is disabled for a Curve that is in
  use by a Fan, and then shows which Fans use it.

6.9.3. Turning Allow zero off raises any point below 20 % to 20 %. The points
stay non-decreasing, because every point below 20 % comes before every point
at or above it.

6.9.4. Curves can be created (**New** in the gallery) and renamed (pencil next
to the name).

6.10. The Curve catalog is loaded on startup and saved automatically on every
valid change.

## 7. Probes

7.1. The Probes catalog is shown in a collapsible panel on the side of the
Curves view. When collapsed, it becomes a narrow rail with a button to expand
it. The panel's open/closed state is remembered.

7.2. Each Probe shows its name, its kind (system or custom), a live value, and
a small sparkline of its recent values.

7.2.1. **Sampling.** The service reads every sensor and evaluates every custom
Probe once per second (four times per second during a Speed pulse). Each
reading is pushed to the GUI straight away, so live values update every second.

7.2.2. **History.** Once per second, whatever the tick rate, the service
records each Probe's value in a two-minute history. A reading that fails is
recorded as a gap. The GUI receives this history when it connects, so
sparklines show real recent data immediately. From then on it adds exactly one
point per service sample. Replies to the user's own changes never add points.

7.2.3. **Sparklines** plot the last 60 seconds of that history. The time axis
is fixed, newest at the right. A history shorter than 60 seconds fills in from
the right rather than being stretched, and missing readings show as gaps. The
vertical scale fits the values shown, but never magnifies a range smaller than
1 °C, so sensor noise doesn't look like large swings. The probe editor's
preview uses the same history, recomputing the expression for each past
second. In read-only mode (1.10) the GUI samples the sensors itself, once per
second. The System section lists the aliases
(7.3.3) first. The remaining sensors are behind a "More sensors (N)" toggle.
Custom Probes can be opened for editing and deleted from their dialog.

7.3. System Probes:

7.3.1. The system's temperature sensors are the base set of Probes.

7.3.2. They are named `sys.foo`. `foo` is the chip and the sensor's label,
lower-cased, with runs of other characters turned into `_`. For example,
k10temp's "Tctl" becomes `sys.k10temp_tctl`. A second chip with the same
driver gets a number (`nvme2`), ordered by device path so names survive
reboots.

7.3.3. These aliases are added when the hardware allows:

- `sys.cpu`: the CPU package temperature (the average if there are several
  CPU packages).
- `sys.gpu`: the GPU edge temperature.
- `sys.nvme`: the first NVMe drive's composite temperature.
- `sys.coolant`: the liquid temperature reported by an AIO cooler.

7.3.4. System Probes are read-only.

7.4. Custom Probes:

7.4.1. The user can define a custom Probe by specifying a name and an
expression.

7.4.2. Custom Probe names must be unique among custom Probes.

7.4.3. Custom Probe names must be valid identifiers: they start with a letter,
followed by letters, digits and `_` only. Because they can never contain a
dot, they can never collide with a system Probe name (`sys.…`).

7.4.4. A custom Probe is referenced everywhere, including in expressions, by
its bare name. For example, a custom Probe named `derp` is used in an
expression as `derp`.

7.4.5. An expression is a valid algebraic expression made of:

- The name of a Probe: a system Probe (for example `sys.cpu` for average CPU
  temperature) or a custom Probe (for example `derp`).
- A floating point number (for example `10`, `0.9`, `.9`).
- An arithmetic operator: add `+`, subtract `-`, multiply `*`, divide `/`,
  exponent `^`.
- Parentheses `(` `)` for grouping.
- A leading minus sign to negate a value (for example `-5 + sys.cpu`).

7.4.6. Operator precedence is conventional: `^` (right-associative) binds
tightest, then `*` `/`, then `+` `-`.

7.4.7. Example: `sys.cpu * .9 + sys.gpu / 10`

7.4.8. Expressions are validated as they are typed. The editor shows the
parsed result's live value, or a message pointing at the error (unknown Probe
with a "did you mean" suggestion, syntax error, circular reference).

7.4.9. Custom Probes must not reference themselves, directly or indirectly.

7.4.10. A custom Probe that is in use by a Fan or by another Probe cannot be
deleted; the app lists what uses it.

7.5. If a Probe cannot be evaluated (sensor missing, division by zero), Fans
using it run at 100 % and show a warning until the Probe recovers.

## 8. Fan control service

8.1. **Default state.** A Fan's default state is its `pwmN_enable` and `pwmN`
values as the service finds them the first time it sees that Fan after boot.
Before its first write to a Fan, the service records them in
`/run/fankata/original.json`. This file lives in memory, so it is cleared on
reboot, and it is only written if it does not already exist. A restarted
service therefore never records Fankata's own manual mode as the default.

8.2. **Taking control** (Unmanaged → Managed). The service sets
`pwmN_enable=1` (manual) and writes the Curve's duty cycle in the same tick.
On every tick it re-asserts manual mode, because some chips reset it after
suspend/resume.

8.3. **Returning to default** (Managed → Unmanaged, service stop, package
removal). For each Fan the service:

1. Stops writing to it.
2. If the original `pwmN_enable` was an automatic mode (2 or higher) or
   0: writes that value back, handing the Fan to its firmware curve.
3. If the original mode was manual (1), or the device has no `pwmN_enable`:
   writes the original `pwmN` value back.
4. If no original `pwmN` was readable (write-only devices): sets 100 %.
5. Reads the values back and reports the result to the GUI. If the chip
   rejects the original mode, the Fan is set to its original `pwmN` in manual
   mode and the GUI shows a warning.

8.4. **Fail-safe** (Windows: 1.12.8). The unit's `ExecStopPost` runs the same restore (8.3), so
Fans return to their defaults even if the service crashes or is killed. The
service uses the systemd watchdog. If its loop stops pinging, systemd kills
and restarts it.

8.5. The service never changes `pwmN_mode` (DC/PWM) or a chip's automatic
curve registers (`pwmN_auto_point*`).

8.6. The service updates every Fan once per second, except a Fan running a
Speed pulse (8.7).

8.7. **Timed tests (Speed pulse).**

8.7.1. The GUI requests a Speed pulse with a socket command naming the Fan.
It requires the same polkit authorization as any other change (1.8).

8.7.2. The service runs the pattern and owns its timer. A pulse ends after
its 8 s pattern, and never runs longer than 15 s. It ends on time even if the
GUI disconnects or crashes.

8.7.3. The service aborts a pulse early when the user presses Stop, or when a
temperature Probe linked to that Fan (its assigned Probe, or `sys.cpu` for
unmanaged Fans) rises above 85 °C.

8.7.4. During the pulse the service samples every fan speed sensor
(`fan*_input`) and reports which of them follow the pulse:

- **The Fan's own sensor follows**: "This control drives this fan."
- **A different sensor follows**: "This control drives fanN's sensor". The
  user is offered to reassign which speed sensor the card shows.
- **No sensor follows**: "No speed change detected". The header may be empty,
  the fan may have no speed sensor, or it may be DC-driven while set to PWM
  mode.

8.7.5. When the pulse ends, a managed Fan resumes its Curve on the next tick.
An unmanaged Fan returns to its default state (8.3), because the pulse put it
into manual mode.

8.7.6. If the service stops during a pulse, the normal fail-safe restore
(8.4) applies.

## 9. Persistence

9.1. (Windows locations: 1.12.6.) The service owns the configuration: Curves (including their Allow zero
flag), custom Probes and Fan assignments. It stores them in a single
human-readable file, `/etc/fankata/config.toml`. Every save writes a temporary
file and renames it into place, so a crash never leaves a half-written file.

9.2. The GUI stores only view preferences (theme, Probes panel open/closed,
the user's Fan card order) in
`~/.config/fankata/`.

9.3. Fans are identified across reboots by driver name and channel, not by
the unstable `hwmonN` index.

## 10. Open questions

10.1. **Parentheses in expressions** (7.4.5) were added because they are needed
to write most real formulas; confirm.

10.2. **Failure behavior** (7.5): run affected Fans at 100 % vs. hand them back
to the system default.

10.3. **Calibrate** is a likely future item for the Fan detail menu (5.4.7).
It would measure each fan's lowest running and lowest restart duty and its
maximum RPM, and could inform the Allow zero floor (6.3.6).

10.4. **Dragging points.** With click-to-remove and click-to-add, dragging a
point to move it is not currently supported. Moving a point means removing
and re-adding it, or editing it in the table.

10.5. **Windows code signing.** The Windows installer and executables are
unsigned, so UAC shows "Unknown publisher" and SmartScreen may warn. An OV or
EV code-signing certificate would remove both.

10.6. **Windows on real hardware.** Fan control on Windows has only been
exercised against simulated hardware. It still needs testing on real boards
with LibreHardwareMonitor-supported fan chips, including the behaviour in
1.12.8 after a crash.

10.7. **Troubleshooting on real hardware.** The Linux steps in 4.7.3 are tested
against `sensors-detect` 3.6.0's output format and a simulated kernel, not on
real boards. Which ITE chips a given kernel's `it87` supports, the community
driver's install steps, and which kernels have `ignore_resource_conflict`
(believed 6.2 and newer for the in-kernel `it87`) still need confirming on
real Gigabyte and other boards. The app decides from what the installed
driver reports, not from a list of chips.
