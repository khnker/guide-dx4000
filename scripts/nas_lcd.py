#!/usr/bin/env python3
import os
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
WARN_USAGE = 70

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
            traceback.print_exc()
            time.sleep(1)


def get_storage_overview():
    tot = used = 0
    warns = []
    for line in sh("df -P -x tmpfs -x devtmpfs").splitlines()[1:]:
        fs, blocks, u, avail, cap = line.split()[:5]
        if not fs.startswith("/dev/sd"):
            continue
        pct = int(cap.rstrip("%"))
        tot += int(blocks)
        used += int(u)
        if pct > WARN_USAGE:
            warns.append(f"{fs[5:].rstrip('0123456789')}:{pct}%")
    ov = (used * 100 + tot // 2) // tot if tot else 0
    return ov, used, tot - used, sorted(warns, key=lambda w: -int(w.split(":")[1][:-1]))[:2]


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
    send(s, "widget_add dash bar string")
    send(s, "widget_add dash rhs string")
    send(s, "widget_set dash hd 1 1 STO\\ [")
    send(s, "set_char 1 28 28 28 28 28 28 28 28")
    send(s, "set_char 2 31 31 31 31 31 31 31 31")

    threading.Thread(target=btn_thread, daemon=True).start()

    prev_bar = None
    prev_pct = None
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
                    prev_bar = None
                    prev_pct = None
                    prev_f2 = None
                    send(s, "widget_set dash hd 1 1 STO\\ [")
                    s.sendall(b"widget_set dash hd2 1 2 \\ \n")
                else:
                    prev_l1 = prev_l2 = None
                was_all = is_all
            if is_all:
                ov, used, free, warns = get_storage_overview()
                units = ov * 14 // 100
                full, half = divmod(units, 2)
                bar = b"".join(
                    b"\x02" if i < full
                    else (b"\x01" if (half and i == full) else b"_")
                    for i in range(7)
                )
                if bar != prev_bar:
                    prev_bar = bar
                    s.sendall(b"widget_set dash bar 6 1 " + bar + b"\n")
                pctv = f"{ov:02d}%"
                if pctv != prev_pct:
                    prev_pct = pctv
                    send(s, f"widget_set dash rhs 13 1 ]{pctv}")
                tot_kb = used + free
                f2 = (f"{used / (1 << 30):04.1f}/{tot_kb / (1 << 30):04.1f}\\ TB"
                      if not warns else " ".join(warns)).encode()
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