#!/usr/bin/env python3
import socket
import subprocess
import time

LCD_HOST = "127.0.0.1"
LCD_PORT = 13666
INTERVAL = 2


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def get_core_temp():
    try:
        return int(open("/sys/class/hwmon/hwmon0/temp2_input").read().strip()) // 1000
    except (IOError, ValueError):
        return 0


def get_storage_overview():
    try:
        total = used = 0
        for line in sh("df -P -x tmpfs -x devtmpfs").splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 4 and cols[0].startswith("/dev/sd"):
                used += int(cols[2]) * 1024
                total += int(cols[1]) * 1024
        ov = int(used * 100 / total) if total else 0
        g = lambda b: b / (1024 ** 4)
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
                temp = get_core_temp()
                ov, used, tot = get_storage_overview()

                filled = min(6, ov * 6 // 100)
                bar = "#" * filled + "." * (6 - filled)
                l1 = f"{temp:02d}C [{bar}] {ov:02d}%".ljust(16)
                l2 = f"{ov:02d}%_{used:03.1f}/{tot:03.1f}TB"

                s.sendall(f"widget_set dash hd 1 1 {l1}\n".encode())
                s.sendall(f"widget_set dash hd2 1 2 {l2}\n".encode())

                time.sleep(INTERVAL)
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    main()
