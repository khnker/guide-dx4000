#!/usr/bin/env python3
import os
import re
import socket
import subprocess
import threading
import time

LCD_HOST = "127.0.0.1"
LCD_PORT = 13666
INTERVAL = 2

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def get_cpu_temp():
    out = sh("sensors coretemp-isa-0000 2>/dev/null")
    m = re.search(r"Core 0:\s+\+?(-?\d+)", out)
    return int(m.group(1)) if m else 0

def get_storage_overview():
    try:
        total = used = 0
        for line in sh("df -P -x tmpfs -x devtmpfs").splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 4:
                used += int(cols[2]) * 1024
                total += int(cols[1]) * 1024
        ov = int(used * 100 / total) if total else 0
        g = lambda b: b / (1024**3)
        return ov, g(used), g(total)
    except Exception:
        return 0, 0.0, 0.0

def main():
    while True:
        try:
            s = socket.create_connection((LCD_HOST, LCD_PORT), timeout=5)
            s.sendall(b"hello\n")
            s.sendall(b"client_set -name nas-dash\n")
            s.sendall(b"screen_add dash\n")
            s.sendall(b"screen_set dash -priority alert\n")
            s.sendall(b"widget_add dash hd string\n")
            s.sendall(b"widget_add dash hd2 string\n")

            while True:
                temp = get_cpu_temp()
                ov, used, tot = get_storage_overview()
                
                l1 = f"{temp:02d}C_STO"
                l2 = f"{ov:02d}%_{used:04.1f}/{tot:04.1f}TB"

                s.sendall(f"widget_set dash hd 1 1 {l1}\n".encode())
                s.sendall(f"widget_set dash hd2 1 2 {l2}\n".encode())
                
                time.sleep(INTERVAL)
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    main()
