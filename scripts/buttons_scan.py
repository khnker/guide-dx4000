#!/usr/bin/env python3
import os
import time

fd = os.open("/dev/port", os.O_RDWR)


def wr(port, v):
    os.lseek(fd, port, 0)
    os.write(fd, bytes([v]))


def rd(port):
    os.lseek(fd, port, 0)
    return os.read(fd, 1)[0]


def unlock():
    wr(0x4E, 0x87)
    wr(0x4E, 0x87)
    wr(0x4E, 0x07)
    wr(0x4F, 0x07)


base = [0xE0, 0xE1, 0xE2, 0xE3, 0xE8, 0xE9, 0xEA, 0xEB, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6]
prev = {}
for r in base:
    prev[r] = None


def snapshot():
    unlock()
    vals = {}
    for r in base:
        wr(0x4E, r)
        vals[r] = rd(0x4F)
    return vals


print("monitoreando:", ", ".join(f"{r:02x}" for r in base))
print("presiona arriba/abajo. Ctrl+C para salir.")
try:
    while True:
        v = snapshot()
        changes = [f"{r:02x}:{v[r]:02x}" for r in base if prev[r] is not None and prev[r] != v[r]]
        if changes:
            print(time.strftime("%H:%M:%S"), " | ".join(changes))
            prev = v
        elif prev[base[0]] is None:
            prev = v
        time.sleep(0.15)
except KeyboardInterrupt:
    pass
finally:
    os.close(fd)