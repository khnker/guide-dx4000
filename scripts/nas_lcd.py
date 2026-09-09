#!/usr/bin/env python3
import os
import re
import socket
import subprocess
import time
import logging

LCD_HOST = "127.0.0.1"
LCD_PORT = 13666
INTERVAL = 2

logging.basicConfig(
    filename="/tmp/nas_lcd.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def get_core_temp():
    try:
        return int(open("/sys/class/hwmon/hwmon0/temp2_input").read().strip()) // 1000
    except (IOError, ValueError) as e:
        logging.warning(f"get_core_temp error: {e}")
        return 0

def get_cputin_temp():
    try:
        return int(open("/sys/class/hwmon/hwmon1/temp3_input").read().strip()) // 1000
    except (IOError, ValueError) as e:
        logging.warning(f"get_cputin_temp error: {e}")
        return 0

def get_fan_pwm():
    try:
        return int(open("/sys/class/hwmon/hwmon1/pwm2").read().strip())
    except (IOError, ValueError) as e:
        logging.warning(f"get_fan_pwm error: {e}")
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
    except Exception as e:
        logging.error(f"get_storage_overview error: {e}")
        return 0, 0.0, 0.0

def send(s, cmd):
    try:
        s.sendall((cmd + "\n").encode())
        logging.debug(f"SENT: {cmd}")
    except Exception as e:
        logging.error(f"SEND error on '{cmd}': {e}")
        raise

def main():
    logging.info("Starting nas_lcd main loop")
    while True:
        try:
            logging.info(f"Connecting to LCDd at {LCD_HOST}:{LCD_PORT}")
            s = socket.create_connection((LCD_HOST, LCD_PORT), timeout=5)
            send(s, "hello")
            send(s, "client_set -name nas-dash")
            send(s, "screen_add dash")
            send(s, "screen_set dash -priority alert")
            send(s, "widget_add dash hd string")
            send(s, "widget_add dash hd2 string")
            time.sleep(0.5)

            while True:
                temp = get_core_temp()
                cputin = get_cputin_temp()
                pwm = get_fan_pwm()
                ov, used, tot = get_storage_overview()

                l1 = f"{temp:02d}C\\ {cputin:02d}C\\ P{pwm:02d}"
                l2 = f"{ov:02d}%{used:03.1f}/{tot:03.1f}TB"

                send(s, f"widget_set dash hd 1 1 {l1}")
                send(s, f"widget_set dash hd2 1 2 {l2}")

                time.sleep(INTERVAL)
        except Exception as e:
            logging.error(f"Main loop exception: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
