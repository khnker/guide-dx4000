#!/usr/bin/env python3
"""
DX4000 CGRAM icon test via LCDd set_char protocol.
"""
import socket
import time

HOST = "127.0.0.1"
PORT = 13666

GLYPHS = [
    ("DOWN",    "4 4 4 4 14 4 0 0"),
    ("UP",      "4 4 4 14 4 4 4 0"),
    ("DISK",    "14 31 17 21 17 31 14 0"),
    ("TEMP",    "4 4 4 4 14 14 31 14"),
    ("FAN",     "20 12 31 6 5 0 0 0"),
    ("OK",      "1 3 6 12 24 8 0 0"),
    ("ALERT",   "4 14 14 14 4 0 4 0"),
    ("ACT",     "0 4 12 31 6 4 0 0"),
]


def lcd_cmd(s, cmd):
    s.sendall((cmd + "\n").encode())
    time.sleep(0.2)
    try:
        return s.recv(1024).decode()
    except:
        return ""


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect((HOST, PORT))

    lcd_cmd(s, "hello")
    lcd_cmd(s, "client_set -name icons")
    lcd_cmd(s, "screen_add I")
    lcd_cmd(s, "screen_set I -priority alert")
    lcd_cmd(s, "widget_add I L1 string")
    lcd_cmd(s, "widget_add I L2 string")

    # Upload all 8 CGRAM glyphs
    for i, (name, vals) in enumerate(GLYPHS):
        r = lcd_cmd(s, f"set_char {i} {vals}")
        print(f"slot {i:2d} {name:10s} {vals:30s} -> {r.strip()}")

    time.sleep(0.5)

    # Show each glyph one at a time
    for i, (name, _) in enumerate(GLYPHS):
        lcd_cmd(s, f"widget_set I L1 1 1 {{{name}}}")
        lcd_cmd(s, "widget_set I L2 1 1 {" + chr(i) + "}")
        time.sleep(1.5)

    # Show all 8 together for 5 seconds
    lcd_cmd(s, "widget_set I L1 1 1 {" + "".join(chr(i) for i in range(8)) + "}")
    lcd_cmd(s, "widget_set I L2 1 2 {ALL 8 ICONS}")
    time.sleep(5)

    s.close()
    print("Done")


if __name__ == "__main__":
    main()
