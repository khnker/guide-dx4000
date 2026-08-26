# Guía de instalación WD DX4000 (Debian + Fan + LCD)

Guía personal basada en:
- https://github.com/alexhorner/WD-DX4000-Installer (instalación solderless)
- https://github.com/alexhorner/WD-DX4000 (post-instalación: fan + LCD)

## 1. Instalación de Debian (installer solderless)

1. Descargar ISO del instalador desde Releases de `alexhorner/WD-DX4000-Installer`.
2. Escribir la ISO en un pen drive:
   - **NO usar Rufus** (rompe parámetros de arranque y deshabilita consola serial).
   - Con `dd` (desde la PC):
     ```bash
     sudo umount /dev/sda
     sudo dd if=/ruta/al/instalador.iso of=/dev/sda bs=4M status=progress
     sudo sync
     ```
     Verificación rápida: `sudo fdisk -l /dev/sda` → deben verse particiones pequeñas de la ISO (en mi caso sdb1 58M, sdb2 4M).
3. Arrancar la DX4000:
   - Equipo **apagado pero enchufado**.
   - Mantener presionado **reset** (trasero, con bolígrafo, evitar metal).
   - Sin soltar reset, pulsar **encendido**.
   - Sostener reset hasta que la LCD muestre **"Loading Recovery"**.
4. Conectar por SSH (tarda hasta 15 min en levantar):
   ```bash
   ssh installer@<IP_DX4000>
   ```
   - Usuario: `installer` / Contraseña: `dx4000`.
   - En la selección de software: marcar **SSH server** y **basic system utilities**. Desactivar escritorio gráfico (no hay video).
5. Post-instalación (el sistema no arranca solo la primera vez):
   - Mantener **reset** de nuevo para arrancar el instalador.
   - En el menú, elegir **Start shell**.
   ```bash
   disk-detect
   modprobe vfat
   cat /proc/partitions      # lsblk NO existe en el shell del instalador
   # En mi caso: sda = disco instalado (sda1 = boot 976M), sdb = pen drive
   mkdir -p /mnt/boot
   mount /dev/sda1 /mnt/boot
   mkdir -p /mnt/usb
   mount /dev/sdb1 /mnt/usb
   cp /mnt/usb/startup.nsh /mnt/boot/
   ls /mnt/boot/startup.nsh
   umount /mnt/usb /mnt/boot
   reboot
   ```

## 2. Configuración final (Fan + LCD) — vía archivos versionados

En Debian Trixie instalado en la DX4000:

```bash
apt-get update
apt-get install lm-sensors fancontrol lcdproc lcdproc-extra-drivers

# Aplicar configs versionados (copiar desde este repo a la DX4000, ver sección 4)
cp configs/fancontrol /etc/fancontrol
cp configs/LCDd.conf /etc/LCDd.conf

# Activar servicios
systemctl enable --now fancontrol lcdproc
```

Los configs aplican solo si los módulos están cargados. Si `sensors` no muestra nada, ver sección 3.

## 3. Detección de sensores (solo la primera vez, o si cambia el kernel)

```bash
/usr/sbin/sensors-detect
```
- **Nota**: `/usr/sbin` puede no estar en el PATH como root, usar ruta completa.
- Respuestas:
  - South bridges scan: **YES**
  - Super I/O scan: **YES**
  - ISA scan: **NO**
  - I2C/SMBus probe: **YES**
  - "scan it?" por cada adapter: **NO**
  - IPMI scan: **YES**
  - Add lines to /etc/modules: **YES**
- Detecta: `nct6775` (Nuvoton NCT5577D) y `coretemp`.
- Reiniciar para cargar módulos (NO usar `/etc/init.d/kmod start`, no existe en Debian actual):
  ```bash
  shutdown -r now
  ```
- Verificar tras boot:
  ```bash
  lsmod | grep -E "nct6775|coretemp"
  sensors
  ```
- Resultado esperado: `coretemp-isa-0000` (Core 0/1) y `nct6776-isa-0a30` con Fan2 (controlado por pwm2) y Pwm3 (brightness LCD).

## 4. Guardar/actualizar configs de la DX4000 en este repo

Desde la PC local:
```bash
scp root@<IP_DX4000>:/etc/fancontrol configs/fancontrol
scp root@<IP_DX4000>:/etc/LCDd.conf configs/LCDd.conf
```

## 5. Brillo LCD

```bash
echo "255" > /sys/class/hwmon/hwmon1/pwm3   # brillo máximo
echo "128" > /sys/class/hwmon/hwmon1/pwm3   # mitad de brillo
```
(0 = apagado, 255 = máximo. Pwm3 es brightness del LCD, NUNCA configurarlo como fan.)

## 6. Mostrar estadísticas en LCD

### Dashboard NAS (16x2, IP + temp CPU / barra de disco, 3 modos + botones)

Script cliente: `scripts/nas_lcd.py` — conecta al daemon LCDd (TCP 127.0.0.1:13666). Muestra:

- **Modo base** (default, vuelve solo tras 4 s sin pulsar):
  - L1: `192.168.100.204 45C` (IP + temp núcleo CPU)
  - L2: `[####......]  5%` (barra 10 chars + uso disco root)
- **Botón ARRIBA** (panel frontal) → **modo RAM**: `RAM 45%` + barra de RAM (de `/proc/meminfo`)
- **Botón ABAJO** → **modo FAN**: `FAN 1636` + `LOAD 0.16` (fan2 rpm + loadavg)

El script arranca un hilo que hace poll del registro de botones del SuperIO cada 20 ms (ver sección 7) y cambia `mode`. Refresco del LCD cada 2 s (`INTERVAL`).

Instalación:
```bash
install -m755 scripts/nas_lcd.py /usr/local/bin/nas_lcd.py
install -m644 scripts/nas-lcd.service /etc/systemd/system/nas-lcd.service
systemctl daemon-reload
systemctl enable --now nas-lcd.service
```

Nota: LCDd por defecto solo escucha TCP `127.0.0.1:13666` (no crea `/tmp/LCDd`).

### Cliente lcdproc manual

```bash
lcdproc -f
lcdproc -h   # ayuda de pantallas
```

Servicio custom (opcional) — auto brillo + stats, editar `/lib/systemd/system/lcdproc.service`:
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

## 7. Botones del panel frontal (SuperIO GPIO)

Los botones ARRIBA/ABAJO del panel frontal se leen por el GPIO del Nuvoton NCT6775 (no hay teclado HD44780 en el LCD). Requiere acceso a `/dev/port` (root + `CONFIG_DEVPORT`).

- Registro SuperIO: `0xE9` (LDN 7), puertos índice `0x4E` / dato `0x4F`, 1 byte.
- Estados (active-low, pull-up): **reposo `0x0C`** · **ARRIBA → bit3 baja `0x04`** · **ABAJO → bit2 baja `0x08`**.
- Secuencia de lectura desde Python (proceso root, p. ej. el servicio):
  ```python
  fd = os.open("/dev/port", os.O_RDWR)
  # unlock + config mode + LDN7 + apuntar reg 0xE9
  for v in (0x87, 0x87, 0x07, 0x07, 0xE9):
      os.lseek(fd, 0x4E, 0); os.write(fd, bytes([v]))
  os.lseek(fd, 0x4F, 0)
  cur = os.read(fd, 1)[0]
  ```
- Detección por flanco de caída (poll), no por nivel: reposo `0x0C`; en `nas_lcd.py` la constante `BTN_RELEASE=0x0C`, `BTN_UP=0x08`, `BTN_DOWN=0x04`.
- ⚠️ **Botón POWER: apaga físicamente el equipo.** Proyectado al interruptor de encendido/EC de la placa: la señal ni llega como evento al SO — probado instalando `acpid` con handler custom (`/etc/acpi/events/powerbtn` → `/usr/local/bin/nas_power`, que solo loguea en `/var/log/nas-power.log`) y **el sistema se apagó igualmente** al presionarlo, sin que el handler se ejecutara (log vacío). Conclusión: POWER NO es usable para menú por software; el menú debe ir con las flechas (p. ej. pulsación larga).

### Trampas encontradas con los botones

- **Pulsación rápida no se detectaba**: con `BTN_POLL=0.1` s una pulsación corta puede caer entera entre dos lecturas y perderse. Bajado a `BTN_POLL=0.02` s (20 ms).
- **"LCD congelado" (pantalla pegada con el último frame)**: el panel HD44780 queda en estado corrupto; se recupera con `systemctl restart lcdproc` (re-inicializa el driver winamp). No es bug de los botones.

## 8. Protocolo LCDd 0.5.9 — píldoras para el dashboard

- LCDd escucha TCP `127.0.0.1:13666` (NO crea `/tmp/LCDd`).
- Setters con guion: `client_set -name X`, `screen_set dash -priority alert`.
- Widgets de texto: `widget_add dash <id> string` ; `widget_set dash <id> <col> <row> <texto>`.
- ⚠️ El texto del widget **NO puede contener espacios** (da `Wrong number of arguments`, ni con comillas). El texto para "limpiar" un widget NO puede ser vacío (`widget_set ... 13 2` → error) ni un espacio; usar un carácter como `.` o `_`.
- `tmp` (col derecha de L1) va en **col 14** si la IP es de 12 chars (192.168.100.204), para que no se pegue.
- Columna derecha (13–16) admite **≤4 chars**, si no se corta fuera de los 16 de la fila.
- `screen_del dash` y cerrar socket limpian en la desconexión; no existe `client_del`.

## 9. OpenMediaVault (OMV)

OMV se instaló en la DX4000 (2026-08-26) con el instalador oficial:

```sh
wget -O - https://get.openmediavault.io | sh -
```

Notas:
- Este comando descarga y lanza el script de instalación de OMV (Debian). Requiere root y conexión a internet en el equipo.
- OMV gestiona su propio stack (web UI en :80, gestión de discos/fstab, SMB/NFS, red). Puede entrar en conflicto con lo que gestionemos manualmente; revisar `fstab`, `samba`, y la red antes/después de usarlo.
- El dashboard LCD, fancontrol y LCDd son independientes de OMV y siguen activos.

## Apéndice A — Regenerar config de fan desde cero (interactivo)

Solo si el config versionado no sirve para un hardware/kernel distinto:

```bash
pwmconfig
```
- ENTER en advertencia (para los fans ~5s, vigilar temperatura).
- "Did you see/hear a fan stopping (n)?" → `y` solo cuando el fan grande se apague.
- Correlación Fan2/Pwm2 (pwm3 NO es fan).
- Sensor fuente: CPU (`hwmon0/temp2_input` o `hwmon0/temp3_input`).
- Low temp: `40` / High temp: `80`.
- PWM stop test: `t` → fan para en 0 (~422 RPM residual).
- PWM start test: `t`, ENTER hasta que el fan gire, luego `y`.
  - ⚠️ Si te pasas con ENTERs, el starting speed queda en 255 (fan ruidoso).
- PWM below low limit: `0` / PWM over high limit: `255`.
- Guardar: opción **4** (Save and quit).

### Si el fan quedó en 255 (ruidoso)
```bash
cat /etc/fancontrol
```
Cambiar `MINPWM=hwmon1/pwm2=255` → `MINPWM=hwmon1/pwm2=2`:
```bash
nano /etc/fancontrol
systemctl restart fancontrol
```

## Apéndice B — Config LCDd (regenerar)

```bash
nano /etc/LCDd.conf
```
Borrar contenido (dejar el aviso cme de arriba) y pegar:
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
Guardar: CTRL+X, Y, ENTER.

## Notas / trampas encontradas

- `lsblk` NO existe en el shell del instalador → usar `cat /proc/partitions`.
- `/etc/init.d/kmod` NO existe en Debian actual (Trixie/Bookworm).
- `/usr/sbin` no está en el PATH como root → `which sensors-detect`/`reboot` fallan; usar ruta completa.
- Como root no se usa `sudo` (no instalado). Ejecutar comandos directos.

## Estado actual

- [x] Debian instalado (vía installer solderless)
- [x] Fan configurado con fancontrol (MINSTART/MINSTOP=2, sensor hwmon0/temp3_input)
- [x] Fancontrol habilitado en boot (PWM2=14 @ boot, fan ~1636 RPM)
- [x] LCDProc instalado y configurado (`configs/LCDd.conf`, winamp/0x378/16x2)
- [x] Servicio lcdproc habilitado y activo (brillo PWM3=255)
- [x] Dashboard NAS en LCD (`scripts/nas_lcd.py` + `nas-lcd.service`): IP + temp / barra disco
- [x] **Botones del panel frontal** integrados en el dashboard: ARRIBA→RAM, ABAJO→FAN (poll SuperIO 0xE9, 20 ms)
- [x] Despliegue actual verificado funcionando (dashboard 3 modos + botones)
- [x] Configs versionados en este repo: `configs/fancontrol`, `configs/LCDd.conf`, `scripts/`
- [x] **OpenMediaVault** instalado (vía `wget -O - https://get.openmediavault.io | sh -`, ver sección 9)

## Apéndice C — Definición del LCD del DX4000

- **Módulo**: HD44780 (o compatible) de **16 columnas × 2 filas** = 32 caracteres.
- **Interfaz**: puerto paralelo LPT `0x378`, modo **winamp** (chip KS0074/HD44780, `ConnectionType=winamp`, `Keypad=no`, `Backlight=no`).
- **Como se controla**: por software vía el daemon **LCDproc (LCDd 0.5.9)**, no directo al hardware. El dashboard es un cliente del daemon.
- **Brillo/backlight**: el "backlight" del LCD se controla con la salida de ventilador **Pwm3** del nct6775: `echo 255 > /sys/class/hwmon/hwmon1/pwm3` (ver sección 5).
- **Capacidad de texto**: ASCII imprimible de máquina + 8 caracteres custom (CG-RAM). Como el driver `hd44780` usa el juego de caracteres estándar, **no hay soporte fiable de caracteres acentuados**; usar ASCII.
- **Qué widgets soporta LCDd** (protocolo 0.3): `string` (texto de 1 palabra), `hbar`/`vbar` (barras), `scroller` (texto que se desplaza), `title`, `frame`, `icon`. El dashboard actual usa solo `string`.
- **Reglas para mostrar info** (resumen de la sección 8):
  - Texto sin espacios (1 token). Para separar elementos usar columnas (widgets en col 1, 14/13, etc.).
  - Columna derecha (13–16): máximo 4 caracteres.
  - Refresco recomendado: 2 s (el LCD muestra texto estático sin parpadeo).

## Credenciales DX4000

- IP: `192.168.100.204`
- Usuario SSH: `usuario` / `PASS_CAMBIA`
- Root (vía `su`): `pi.ROOT_PASS`
- SSH root: `ssh root@<ip>` (RootSSH habilitado)