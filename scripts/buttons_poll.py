#!/usr/bin/env python3
import os
import time

PORT = "/dev/port"


def wr(port, v):
    os.lseek(fd, port, 0)
    os.write(fd, bytes([v]))


def rd(port):
    os.lseek(fd, port, 0)
    return os.read(fd, 1)[0]


fd = os.open(PORT, os.O_RDWR)
wr(0x4E, 0x87)
wr(0x4E, 0x87)
wr(0x4E, 0x07)
wr(0x4F, 0x07)
wr(0x4E, 0xE9)

last = rd(0x4F)
print(f"estado inicial 0xE9 = 0x{last:02x} (bits {last:08b})")
print("Presiona cada boton y mira que bit cambia. Ctrl+C para salir.")

try:
    while True:
        cur = rd(0x4F)
        if cur != last:
            changed = last ^ cur
            print(f"{time.strftime('%H:%M:%S')} 0x{cur:02x} bits {cur:08b} "
                  f"(cambiaron {changed:08b}) presionado={cur:08b}")
            last = cur
            time.sleep(0.2)
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    os.close(fd)