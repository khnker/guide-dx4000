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


def send(s, cmd):
    s.sendall((cmd + "\n").encode())


def main():
    while True:
        try:
            s = socket.create_connection((LCD_HOST, LCD_PORT), timeout=5)
            send(s, "hello")
            send(s, "client_set -name nas-dash")
            send(s, "screen_add dash")
            send(s, "screen_set dash -priority alert")
            send(s, "widget_add dash hd string")
            send(s, "widget_add dash hd2 string")
            time.sleep(0.5)

            while True:
                try:
                    temp = get_core_temp()
                    ov, used, tot = get_storage_overview()

                    filled = min(6, ov * 6 // 100)
                    bar = ("#" * filled).ljust(6, ".")
                    l1 = f"{temp:02d}C"
                    l2 = f"{used:03.1f}/{tot:03.1f}TB".ljust(16)

                    send(s, f"widget_set dash hd 1 1 {l1}")
                    send(s, f"widget_set dash hd2 1 2 {l2}")
                except Exception as e:
                    print(f"Error updating LCD: {e}")
                time.sleep(INTERVAL)
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    main()
