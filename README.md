# WD Sentinel DX4000

Setup guide and tooling to turn a WD Sentinel DX4000 into a Debian server with a working front LCD.

| Path | Description |
|------|-------------|
| `README.md` | **Complete installation guide** (this file) |
| `configs/fancontrol` | fancontrol config (PWM2 superIO nct6775, MINTEMP=40 / MAXTEMP=80) |
| `configs/LCDd.conf` | lcdproc config (hd44780 driver, ConnectionType=winamp, Port=0x378) |
| `scripts/nas_lcd.py` | LCD dashboard: all/up/fan/ip/ram screens + front-panel buttons via SuperIO |
| `scripts/buttons_poll.py` / `buttons_scan.py` | Button polling/scanning utilities |
| `scripts/nas-lcd.service` | systemd unit for the dashboard |

## Dashboard (nas_lcd.py)

A single LCDd screen `dash` with 2 string widgets (`hd`/`hd2`) — this is more stable than 2 priority-switched screens (those froze the HD44780 module).

- **Screens** (navigated with the panel arrows): `all` (bay grid + usage %), `up` (uptime), `fan` (RPM/LOAD), `ip`, `ram`
- **CGRAM**: 1..5 = bay disks, 6 = system SSD, 7 = degree symbol. Barrel level 0..7, -1 = missing
- **Hardware interaction**: requires LCDd patched with `set_char`

Requires a patched LCDd 0.5.9 with the `set_char` command.

## Deploy

```bash
python3 -m py_compile scripts/nas_lcd.py
scp scripts/nas_lcd.py root@<ip>:/usr/local/bin/nas_lcd.py
ssh root@<ip> 'chmod 755 /usr/local/bin/nas_lcd.py && systemctl restart nas-lcd && systemctl is-active nas-lcd'
```

If the LCD freezes: `systemctl restart lcdproc`.

---

# Installation guide (Debian + Fan + LCD)

Personal guide based on:
- https://github.com/alexhorner/WD-DX4000-Installer (solderless installer)
- https://github.com/alexhorner/WD-DX4000 (post-install: fan + LCD)

## 1. Installing Debian (solderless installer)

1. Download the installer ISO from the Releases of `alexhorner/WD-DX4000-Installer`.
2. Write the ISO to a USB stick:
   - **Do NOT use Rufus** (it breaks the boot parameters and disables the serial console).
   - Use `dd` (from your PC):
     ```bash
     sudo umount /dev/sda
     sudo dd if=/path/to/installer.iso of=/dev/sda bs=4M status=progress
     sudo sync
     ```
     Quick check: `sudo fdisk -l /dev/sda` → you should see the small ISO partitions (mine showed sdb1 58M, sdb2 4M).
3. Boot the DX4000:
   - Unit **off but plugged in**.
   - Hold **reset** (back panel, with a pen, avoid metal).
   - While holding reset, press **power**.
   - Keep holding reset until the LCD shows **"Loading Recovery"**.
4. Connect via SSH (takes up to 15 min to come up):
   ```bash
   ssh installer@<IP_DX4000>
   ```
   - User: `installer` / Password: `dx4000`.
   - In the software selection: mark **SSH server** and **basic system utilities**. Disable the graphical desktop (no video).
5. Post-install (the system does not boot by itself the first time):
   - Hold **reset** again to boot the installer.
   - In the menu choose **Start shell**.
   ```bash
   disk-detect
   modprobe vfat
   cat /proc/partitions      # lsblk does NOT exist in the installer shell
   # Mine: sda = installed disk (sda1 = boot 976M), sdb = USB stick
   mkdir -p /mnt/boot
   mount /dev/sda1 /mnt/boot
   mkdir -p /mnt/usb
   mount /dev/sdb1 /mnt/usb
   cp /mnt/usb/startup.nsh /mnt/boot/
   ls /mnt/boot/startup.nsh
   umount /mnt/usb /mnt/boot
   reboot
   ```

## 2. Final config (Fan + LCD) — via versioned files

On the Debian Trixie installed on the DX4000:

```bash
apt-get update
apt-get install lm-sensors fancontrol lcdproc lcdproc-extra-drivers

# Apply versioned configs (copy from this repo to the DX4000, see section 4)
cp configs/fancontrol /etc/fancontrol
cp configs/LCDd.conf /etc/LCDd.conf

# Enable services
systemctl enable --now fancontrol lcdproc
```

The configs only apply if the modules are loaded. If `sensors` shows nothing, see section 3.

## 3. Sensor detection (only first time, or after a kernel change)

```bash
/usr/sbin/sensors-detect
```
- **Note**: `/usr/sbin` may not be on root's PATH, use the full path.
- Answers:
  - South bridges scan: **YES**
  - Super I/O scan: **YES**
  - ISA scan: **NO**
  - I2C/SMBus probe: **YES**
  - "scan it?" per adapter: **NO**
  - IPMI scan: **YES**
  - Add lines to /etc/modules: **YES**
- Detects: `nct6775` (Nuvoton NCT5577D) and `coretemp`.
- Reboot to load modules (do NOT use `/etc/init.d/kmod start`, it doesn't exist on current Debian):
  ```bash
  shutdown -r now
  ```
- Verify after boot:
  ```bash
  lsmod | grep -E "nct6775|coretemp"
  sensors
  ```
- Expected: `coretemp-isa-0000` (Core 0/1) and `nct6776-isa-0a30` with Fan2 (controlled by pwm2) and Pwm3 (LCD brightness).

## 4. Saving/updating the DX4000 configs in this repo

From the local PC:
```bash
scp root@<IP_DX4000>:/etc/fancontrol configs/fancontrol
scp root@<IP_DX4000>:/etc/LCDd.conf configs/LCDd.conf
```

## 5. LCD brightness

```bash
echo "255" > /sys/class/hwmon/hwmon1/pwm3   # maximum brightness
echo "128" > /sys/class/hwmon/hwmon1/pwm3   # half brightness
```
(0 = off, 255 = maximum. Pwm3 is the LCD brightness, NEVER set it up as a fan.)

## 6. Showing stats on the LCD

### NAS dashboard (16x2, IP + CPU temp / disk bar, 3 modes + buttons)

Client script: `scripts/nas_lcd.py` — connects to the LCDd daemon (TCP 127.0.0.1:13666). Shows:

- **Base mode** (default, returns after 4 s without input):
  - L1: `192.168.100.204 45C` (IP + CPU core temp)
  - L2: `[####......]  5%` (10-char bar + root disk usage)
- **UP button** (front panel) → **RAM mode**: `RAM 45%` + RAM bar (from `/proc/meminfo`)
- **DOWN button** → **FAN mode**: `FAN 1636` + `LOAD 0.16` (fan2 rpm + loadavg)

The script runs a thread polling the SuperIO buttons register every 20 ms (see section 7) and changes `mode`. LCD refresh every 2 s (`INTERVAL`).

Install:
```bash
install -m755 scripts/nas_lcd.py /usr/local/bin/nas_lcd.py
install -m644 scripts/nas-lcd.service /etc/systemd/system/nas-lcd.service
systemctl daemon-reload
systemctl enable --now nas-lcd.service
```

Note: LCDd only listens on TCP `127.0.0.1:13666` by default (it does not create `/tmp/LCDd`).

### Manual lcdproc client

```bash
lcdproc -f
lcdproc -h   # screen help
```

Optional custom service — auto brightness + stats, edit `/lib/systemd/system/lcdproc.service`:
```
[Unit]
Description=LCD display daemon
Documentation=man:LCDd(8) http://www.lcdproc.org/

[Service]
User=root
ExecStartPre=bash -c "echo \"255\" > /sys/class/hwmon/hwmon1/pwm3"
ExecStart=/usr/sbin/LCDd -s 1 -f -c /etc/LCDd.conf
ExecStartPost=bash -c "sleep 5 && lcdproc C P M U S K"
ExecStop=bash -c "echo \"128\" > /sys/class/hwmon/hwmon1/pwm3"

[Install]
WantedBy=multi-user.target
```

## 7. Front-panel buttons (SuperIO GPIO)

The UP/DOWN buttons of the front panel are read via the Nuvoton NCT6775 GPIO (there's no HD44780 keypad on the LCD). Requires access to `/dev/port` (root + `CONFIG_DEVPORT`).

- SuperIO register: `0xE9` (LDN 7), index port `0x4E` / data port `0x4F`, 1 byte.
- States (active-low, pull-up): **idle `0x0C`** · **UP → bit3 low `0x04`** · **DOWN → bit2 low `0x08`**.
- Read sequence from Python (root process, e.g. the service):
  ```python
  fd = os.open("/dev/port", os.O_RDWR)
  # unlock + config mode + LDN7 + point reg 0xE9
  for v in (0x87, 0x87, 0x07, 0x07, 0xE9):
      os.lseek(fd, 0x4E, 0); os.write(fd, bytes([v]))
  os.lseek(fd, 0x4F, 0)
  cur = os.read(fd, 1)[0]
  ```
- Detect by falling edge (poll), not level: idle `0x0C`; in `nas_lcd.py` the constants are `BTN_RELEASE=0x0C`, `BTN_UP=0x08`, `BTN_DOWN=0x04`.
- ⚠️ **The POWER button physically powers off the unit.** It is wired to the power switch/EC of the board: the signal never reaches the OS as an event — tested by installing `acpid` with a custom handler (`/etc/acpi/events/powerbtn` → `/usr/local/bin/nas_power`, which only logs to `/var/log/nas-power.log`) and **the system powered off anyway** when pressed, without the handler ever running (empty log). Conclusion: POWER is NOT usable for a software menu; the menu must use the arrows (e.g. long press).

### Gotchas found with the buttons

- **Fast presses were missed**: with `BTN_POLL=0.1` s a short press could fall entirely between two reads. Lowered to `BTN_POLL=0.02` s (20 ms).
- **"Frozen LCD" (stuck on the last frame)**: the HD44780 panel ends in a corrupted state; recover with `systemctl restart lcdproc` (re-initializes the winamp driver). Not a button bug.

## 8. LCDd 0.5.9 protocol — dashboard pills

- LCDd listens on TCP `127.0.0.1:13666` (it does NOT create `/tmp/LCDd`).
- Setters use dashes: `client_set -name X`, `screen_set dash -priority alert`.
- Text widgets: `widget_add dash <id> string` ; `widget_set dash <id> <col> <row> <text>`.
- ⚠️ The widget **text must not contain spaces** (`Wrong number of arguments`, even with quotes). The "clear" text must not be empty (`widget_set ... 13 2` → error) nor a space; use a character like `.` or `_`.
- `tmp` (right column of L1) goes on **col 14** if the IP is 12 chars long (192.168.100.204), to avoid clipping.
- The right column (13–16) fits **≤4 chars**, otherwise it gets cut beyond the 16-column row.
- `screen_del dash` and closing the socket clean up on disconnect; there is no `client_del`.

## 9. OpenMediaVault (OMV)

OMV was installed on the DX4000 (2026-08-26) using the official installer:

```sh
wget -O - https://get.openmediavault.io | sh -
```

Notes:
- This downloads and runs the OMV install script (Debian). Requires root and internet access on the unit.
- OMV manages its own stack (web UI on :80, disk/fstab management, SMB/NFS, network). It can conflict with what we manage manually; review `fstab`, `samba`, and the network before/after using it.
- The LCD dashboard, fancontrol and LCDd are independent of OMV and keep running.

## Appendix A — Regenerating the fan config from scratch (interactive)

Only if the versioned config does not fit other hardware/kernel:

```bash
pwmconfig
```
- ENTER through the warning (stops the fans ~5s, watch the temperature).
- "Did you see/hear a fan stopping (n)?" → `y` only when the big fan actually stops.
- Correlation Fan2/Pwm2 (pwm3 is NOT a fan).
- Source sensor: CPU (`hwmon0/temp2_input` or `hwmon0/temp3_input`).
- Low temp: `40` / High temp: `80`.
- PWM stop test: `t` → fan stops at 0 (~422 RPM residual).
- PWM start test: `t`, ENTER until the fan spins, then `y`.
  - ⚠️ If you overdo the ENTERs, the starting speed stays at 255 (noisy fan).
- PWM below low limit: `0` / PWM over high limit: `255`.
- Save: option **4** (Save and quit).

### If the fan ended up at 255 (noisy)
```bash
cat /etc/fancontrol
```
Change `MINPWM=hwmon1/pwm2=255` → `MINPWM=hwmon1/pwm2=2`:
```bash
nano /etc/fancontrol
systemctl restart fancontrol
```

## Appendix B — LCDd config (regenerate)

```bash
nano /etc/LCDd.conf
```
Clear the content (leave the top notice) and paste:
```
[server]
DriverPath=/usr/lib/x86_64-linux-gnu/lcdproc/
Driver=hd44780
ServerScreen=no
Heartbeat=off

[menu]

[hd44780]
ConnectionType=winamp
Port=0x378
bidirectional=yes
Speed=0
Keypad=no
Backlight=no
Size=16x2
DelayBus=no
```
Save: CTRL+X, Y, ENTER.

## Notes / gotchas

- `lsblk` does NOT exist in the installer shell → use `cat /proc/partitions`.
- `/etc/init.d/kmod` does NOT exist on current Debian (Trixie/Bookworm).
- `/usr/sbin` is not on root's PATH → `which sensors-detect`/`reboot` fail; use the full path.
- As root `sudo` is not used (not installed). Run commands directly.

## Current status

- [x] Debian installed (via solderless installer)
- [x] Fan configured with fancontrol (MINSTART/MINSTOP=2, sensor hwmon0/temp3_input)
- [x] Fancontrol enabled at boot (PWM2=14 @ boot, fan ~1636 RPM)
- [x] LCDProc installed and configured (`configs/LCDd.conf`, winamp/0x378/16x2)
- [x] lcdproc service enabled and active (brightness PWM3=255)
- [x] LCD NAS dashboard (`scripts/nas_lcd.py` + `nas-lcd.service`)
- [x] **Front-panel buttons** integrated in the dashboard (SuperIO 0xE9 poll, 20 ms)
- [x] **OpenMediaVault** installed (via `wget -O - https://get.openmediavault.io | sh -`, see section 9)

## Appendix C — DX4000 LCD definition

- **Module**: HD44780 (or compatible) **16 columns × 2 rows** = 32 characters.
- **Interface**: parallel port LPT `0x378`, **winamp** mode (KS0074/HD44780 chip, `ConnectionType=winamp`, `Keypad=no`, `Backlight=no`).
- **How it's driven**: by software via the **LCDproc (LCDd 0.5.9)** daemon, not directly from hardware. The dashboard is a daemon client.
- **Brightness/backlight**: the LCD "backlight" is controlled with the fan output **Pwm3** of the nct6775: `echo 255 > /sys/class/hwmon/hwmon1/pwm3` (see section 5).
- **Text capacity**: printable ASCII + 8 custom characters (CG-RAM). Since the `hd44780` driver uses the standard character set there is **no reliable accent support**; use ASCII.
- **LCDd widget types** (protocol 0.3): `string` (single-word text), `hbar`/`vbar` (bars), `scroller` (scrolling text), `title`, `frame`, `icon`. The current dashboard uses only `string`.
- **Display rules** (summary of section 8):
  - Text without spaces (1 token); for real spaces use the `\ ` escape inside the token.
  - Right column (13–16): 4 characters max.
  - Refresh recommended: 2 s (the LCD renders static text without flicker).

## Original sources

- https://github.com/alexhorner/WD-DX4000-Installer — solderless installer
- https://github.com/alexhorner/WD-DX4000 — post-install (fan + LCD)
- https://github.com/alexhorner/WD-DX4000-IO — I/O access demo (SuperIO 0xE9 buttons)
- https://lcdproc.org / https://github.com/lcdproc/lcdproc — LCDproc (LCDd)
- https://github.com/lcdproc/lcdproc/issues/98 — "Expose set_char and get_free_char" (basis of the `set_char` patch)
- https://get.openmediavault.io — OpenMediaVault installer
- HD44780 LCD controller datasheet (Hitachi) — charset and CGRAM