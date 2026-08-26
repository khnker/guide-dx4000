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
BTN_LONG = 1.5

BTN_RELEASE = 0x0C
BTN_UP = 0x08
BTN_DOWN = 0x04

N_SLOTS = 6

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


def get_cpu_temp():
    out = sh("sensors coretemp-isa-0000 2>/dev/null")
    m = re.search(r"Core 0:\s+\+?(-?\d+)", out)
    return int(m.group(1)) if m else 0


def slot_dev(n):
    try:
        blocks = os.listdir(f"/sys/bus/scsi/devices/{n - 1}:0:0:0/block")
    except OSError:
        return None
    return blocks[0] if blocks else None


def get_use(dev):
    part = dev
    with open("/proc/partitions") as f:
        for line in f:
            cols = line.split()
            if len(cols) < 4:
                continue
            p = cols[-1]
            if p.startswith(dev) and p != dev:
                part = p
                break
    line = sh(f"df -P /dev/{part}")
    rows = line.splitlines()
    if len(rows) < 2 or "/dev" not in line:
        return None
    return int(rows[1].split()[4].rstrip("%"))


def get_slot_use(n):
    if n == N_SLOTS:
        return get_use("sda")
    dev = slot_dev(n)
    if dev:
        return get_use(dev)
    return None


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


PRESS_UP = 0x04
PRESS_DOWN = 0x08


def btn_thread():
    global mode, mode_since
    import traceback
    print("btn_thread start", flush=True)
    while True:
        try:
            prev = BTN_RELEASE
            down_since = 0
            down_btn = 0
            screens = ["all", "up", "fan", "ip", "ram"]
            last_hb = time.time()
            while True:
                cur = btn_state()
                now = time.time()
                if now - last_hb > 5:
                    print(f"HB prev=0x{prev:02x}", flush=True)
                    last_hb = now
                if cur != BTN_RELEASE and prev == BTN_RELEASE:
                    down_since, down_btn = now, cur
                    print(f"BTN dn 0x{cur:02x}", flush=True)
                elif cur == BTN_RELEASE and prev != BTN_RELEASE and down_since:
                    if now - down_since >= BTN_LONG:
                        if down_btn == PRESS_UP:
                            mode, mode_since = "ip", now
                        else:
                            mode = {"all": "ram", "ram": "fan", "fan": "all"}.get(mode, "all")
                            mode_since = now
                    else:
                        idx = screens.index(mode) if mode in screens else 0
                        if down_btn == PRESS_UP:
                            mode, mode_since = screens[(idx + 1) % 5], now
                        elif down_btn == PRESS_DOWN:
                            mode, mode_since = screens[(idx - 1) % 5], now
                    down_since = 0
                prev = cur
                time.sleep(BTN_POLL)
        except Exception:
            print("BTN THREAD CRASH", flush=True)
            traceback.print_exc()
            time.sleep(1)


def get_ram_stats():
    with open("/proc/meminfo") as f:
        total = avail = 0
        for line in f:
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
                break
    used = max(0, total - avail)
    pct = used * 100 // total if total else 0
    g = lambda kb: kb / 1024 / 1024
    return pct, g(used), g(avail)


def get_fan_rpm():
    try:
        return int(open("/sys/class/hwmon/hwmon1/fan2_input").read())
    except (IOError, ValueError):
        return 0


def get_loads():
    parts = open("/proc/loadavg").read().split()
    return parts[0], parts[1]


def get_uptime():
    up = float(open("/proc/uptime").read().split()[0])
    d, r = divmod(int(up), 86400)
    h, m = divmod(r, 3600)
    m //= 60
    if d:
        up_t = f"UPTIME\\ {d}d\\ {h:02d}:{m:02d}"
    else:
        up_t = f"UPTIME\\ {h:02d}:{m:02d}"
    boot = time.strftime("%m/%d %H:%M", time.localtime(time.time() - up))
    return up_t, "Boot\\ " + boot.replace(" ", "\\ ")


def barrel(level):
    rows = []
    for i in range(8):
        if (level == 0 and i == 7) or (level > 0 and i >= 8 - level):
            rows.append("31")
        else:
            rows.append("0")
    return " ".join(rows)


def send_char(s, slot, level):
    if level == -1:
        send(s, f"set_char {slot} 0 0 0 0 0 0 0 0")
    else:
        send(s, f"set_char {slot} {barrel(level)}")


def deg_glyph():
    return "14 17 17 14 0 0 0 0"


def send_hd(s, payload, degree=False):
    b = b"widget_set dash hd 1 1 " + payload
    if degree:
        b += bytes([7])
    s.sendall(b + b"\n")


def send_info(s, line1, line2):
    s.sendall(f"widget_set dash hd 1 1 {line1}\n".encode())
    s.sendall(f"widget_set dash hd2 1 2 {line2}\n".encode())


def main():
    global mode, mode_since
    s = connect()
    send(s, "hello")
    send(s, "client_set -name nas-dash")
    send(s, "screen_add dash")
    send(s, "screen_set dash -priority alert")
    send(s, "widget_add dash hd string")
    send(s, "widget_add dash hd2 string")
    send(s, f"set_char 7 {deg_glyph()}")

    threading.Thread(target=btn_thread, daemon=True).start()

    prev_barrel = {}
    prev_f1 = None
    prev_f2 = None
    prev_l1 = None
    prev_l2 = None
    was_all = True
    try:
        while True:
            if mode != "all" and time.time() - mode_since > BTN_HOLD:
                mode = "all"
            is_all = mode == "all"
            if is_all != was_all:
                if is_all:
                    prev_f1 = None
                    prev_f2 = None
                    prev_barrel = {}
                    s.sendall(b"widget_set dash hd2 1 2 \\ \n")
                else:
                    prev_l1 = prev_l2 = None
                was_all = is_all
            if is_all:
                temp = get_cpu_temp()
                f1 = f"0\\ 1\\ 2\\ 3\\ 4\\ 5\\ {temp}".encode() + bytes([7])
                if f1 != prev_f1:
                    send_hd(s, f1)
                    prev_f1 = f1
                f2 = b"".join(
                    ("--" if u is None else f"{min(u, 99):02d}").encode()
                    for u in (get_use("sda") if ui == 0 else get_slot_use(ui)
                              for ui in range(N_SLOTS))
                )
                if f2 != prev_f2:
                    s.sendall(b"widget_set dash hd2 1 2 " + f2 + b"\n")
                    prev_f2 = f2
            else:
                if mode == "ip":
                    info = (get_ip() + "\\ \\ \\ \\ ", "\\ ")
                elif mode == "up":
                    info = get_uptime()
                elif mode == "ram":
                    pct, ug, fg = get_ram_stats()
                    info = (f"RAM\\ {pct:>2}%\\ {ug:.2f}G",
                            f"FREE\\ {fg:.2f}G\\ /{ug + fg:.1f}G")
                else:
                    l1, l5 = get_loads()
                    info = (f"FAN\\ {get_fan_rpm():>4}\\ RPM",
                            f"LOAD\\ {l1[:4]}\\ {l5[:4]}")
                if (info[0], info[1]) != (prev_l1, prev_l2):
                    send_info(s, info[0], info[1])
                    prev_l1, prev_l2 = info[0], info[1]
            time.sleep(INTERVAL)
    except (KeyboardInterrupt, ConnectionError):
        pass
    finally:
        send(s, "screen_del dash")
        s.close()


if __name__ == "__main__":
    main()