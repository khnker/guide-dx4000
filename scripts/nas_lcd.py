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
BTN_POLL = 0.02
BTN_HOLD = 4
BTN_RELEASE = 0x0C
BTN_UP = 0x08
BTN_DOWN = 0x04
WARN_USAGE = 70

FAN_PWM_PATH = "/sys/class/hwmon/hwmon1/pwm2"
FAN_RPM_PATH = "/sys/class/hwmon/hwmon1/fan2_input"
FAN_MIN = 10
FAN_MAX = 255
FAN_STEP = 2
FAN_TARGET = 42
FAN_HARD_LIMIT = 55
FAN_INTERVAL = 5

mode = "all"
mode_since = 0
btn_fd = None
btn_lock = threading.Lock()


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def get_ip():
    for line in sh("hostname -I").split():
        if "." in line:
            return line
    return "???"


def get_core_temp():
    try:
        out = open("/sys/class/hwmon/hwmon0/temp2_input").read()
        return int(out.strip()) // 1000
    except (IOError, ValueError):
        try:
            out = sh("sensors coretemp-isa-0000 2>/dev/null")
            m = re.search(r"Core 0:\s+\+?(-?\d+)", out)
            return int(m.group(1)) if m else 40
        except Exception:
            return 40


def get_fan_rpm():
    try:
        return int(open(FAN_RPM_PATH).read())
    except (IOError, ValueError):
        return 0


def set_fan_pwm(val):
    val = max(FAN_MIN, min(FAN_MAX, val))
    try:
        with open(FAN_PWM_PATH, "w") as f:
            f.write(str(val))
    except IOError:
        pass
    return val


def get_fan_pwm():
    try:
        return int(open(FAN_PWM_PATH).read())
    except (IOError, ValueError):
        return FAN_MIN


def get_storage_overview():
    tot = used = 0
    warns = []
    for line in sh("df -P -x tmpfs -x devtmpfs").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        fs, blocks, u, avail, cap = parts[:5]
        if not fs.startswith("/dev/sd"):
            continue
        pct = int(cap.rstrip("%"))
        tot += int(blocks)
        used += int(u)
        if pct > WARN_USAGE:
            warns.append(f"{fs[5:].rstrip('0123456789')}:{pct}%")
    ov = (used * 100 + tot // 2) // tot if tot else 0
    return ov, used, tot - used, sorted(warns, key=lambda w: -int(w.split(":")[1][:-1]))[:2]


def send(sock, cmd):
    sock.sendall(cmd.encode() + b"\n")


def connect():
    return socket.create_connection((LCD_HOST, LCD_PORT), timeout=5)


def btn_open():
    global btn_fd
    btn_fd = os.open("/dev/port", os.O_RDWR)
    _btn_wr(0x4E, 0x87)
    _btn_wr(0x4E, 0x87)
    _btn_wr(0x4E, 0x07)
    _btn_wr(0x4F, 0x07)
    _btn_wr(0x4E, 0xE9)


def _btn_wr(port, v):
    os.lseek(btn_fd, port, 0)
    os.write(btn_fd, bytes([v]))


def btn_state():
    global btn_fd
    with btn_lock:
        if btn_fd is None:
            btn_open()
        os.lseek(btn_fd, 0x4F, 0)
        try:
            return os.read(btn_fd, 1)[0]
        except OSError:
            os.close(btn_fd)
            btn_fd = None
            return BTN_RELEASE


def btn_thread():
    global mode, mode_since
    while True:
        try:
            prev = BTN_RELEASE
            down_since = 0
            down_btn = 0
            screens = ["all", "up", "fan", "ip", "ram"]
            while True:
                cur = btn_state()
                now = time.time()
                if cur != BTN_RELEASE and prev == BTN_RELEASE:
                    down_since, down_btn = now, cur
                elif cur == BTN_RELEASE and prev != BTN_RELEASE:
                    held = now - down_since
                    if held >= 1.5 and down_btn == BTN_RELEASE:
                        idx = screens.index(mode) if mode in screens else 0
                        mode = screens[(idx + 1) % len(screens)]
                        mode_since = now
                    elif held < 0.3:
                        if down_btn == BTN_UP:
                            idx = screens.index(mode) if mode in screens else 0
                            mode = screens[(idx - 1) % len(screens)]
                            mode_since = now
                        elif down_btn == BTN_DOWN:
                            idx = screens.index(mode) if mode in screens else 0
                            mode = screens[(idx + 1) % len(screens)]
                            mode_since = now
                prev = cur
                time.sleep(BTN_POLL)
        except Exception:
            time.sleep(1)


def fan_thread():
    while True:
        try:
            temp = get_core_temp()
            pwm = get_fan_pwm()
            if temp > FAN_HARD_LIMIT:
                pwm = min(FAN_MAX, pwm + FAN_STEP * 2)
            elif temp > FAN_TARGET:
                pwm = min(FAN_MAX, pwm + FAN_STEP)
            elif temp < FAN_TARGET - 2:
                pwm = max(FAN_MIN, pwm - FAN_STEP)
            set_fan_pwm(pwm)
        except Exception:
            pass
        time.sleep(FAN_INTERVAL)


def main():
    global mode, mode_since
    s = connect()
    send(s, "hello")
    send(s, "client_set -name nas-dash")
    send(s, "screen_add dash")
    send(s, "screen_set dash -priority alert")
    send(s, "widget_add dash hd string")
    send(s, "widget_add dash hd2 string")

    threading.Thread(target=btn_thread, daemon=True).start()
    threading.Thread(target=fan_thread, daemon=True).start()

    prev_l1 = None
    prev_l2 = None
    was_all = True
    try:
        while True:
            if mode != "all" and time.time() - mode_since > BTN_HOLD:
                mode = "all"
            is_all = mode == "all"
            if is_all != was_all:
                prev_l1 = prev_l2 = None
                was_all = is_all
            t = get_core_temp()
            ov, used, free, warns = get_storage_overview()
            filled = min(6, ov * 6 // 100)
            bar = "#" * filled + "." * (6 - filled)
            tot_kb = used + free
            if is_all:
                l1 = f"{t:02d}C STO [{bar}]"
                l2 = f"{ov:02d}% {used / (1 << 30):04.1f}/{tot_kb / (1 << 30):04.1f} TB" if not warns else " ".join(warns)
            elif mode == "ip":
                l1 = get_ip()
                l2 = ""
            elif mode == "fan":
                l1 = f"FAN {get_fan_rpm()} RPM"
                l2 = f"PWM {get_fan_pwm()}"
            elif mode == "ram":
                l1 = "RAM"
                l2 = ""
            else:
                l1 = f"{t:02d}C STO [{bar}]"
                l2 = f"{ov:02d}% {used / (1 << 30):04.1f}/{tot_kb / (1 << 30):04.1f} TB"
            if l1 != prev_l1 or l2 != prev_l2:
                s.sendall(f"widget_set dash hd 1 1 {l1}\n".encode())
                s.sendall(f"widget_set dash hd2 1 2 {l2}\n".encode())
                prev_l1, prev_l2 = l1, l2
            time.sleep(INTERVAL)
    except (KeyboardInterrupt, ConnectionError):
        pass
    finally:
        send(s, "screen_del dash")
        s.close()


if __name__ == "__main__":
    main()
