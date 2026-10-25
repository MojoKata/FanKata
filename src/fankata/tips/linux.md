- **Load your board's sensor driver.** Run `sudo sensors-detect`, accept the defaults, then `sudo systemctl restart fankata`.
- **ACPI resource conflict** in `dmesg`: add `acpi_enforce_resources=lax` to the kernel command line and restart.
- **Gigabyte boards** use ITE chips, often two (IT8686E, IT8688E, IT8689E or IT8696E, plus IT8792E or IT87952E). Use the community it87 driver and load it with `ignore_resource_conflict=1` rather than a boot option. `gigabyte_wmi` reads temperatures only.
- **ITE chips** (IT8686E, IT8689E, IT8792E…) need the out-of-tree [it87 driver](https://github.com/frankcrawford/it87). With Secure Boot on, enrol its DKMS signing key.
- **New board, older kernel:** on Ubuntu 22.04 install the HWE kernel.
```
sudo apt install linux-generic-hwe-22.04
```
- **ThinkPad:** fan control needs `options thinkpad_acpi fan_control=1`.
- **BIOS:** set the fan headers to *PWM* or *Auto*, not *Full speed*.
- **Hubs and splitters** share one control, so their fans appear as one.
- **NVIDIA cards** have no fan control in Linux's hwmon interface.
- Still stuck? **Copy report** and attach it to an issue.
