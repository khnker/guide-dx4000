#!/usr/bin/env python3
"""
Example: upload CGRAM glyphs via LCDd set_char protocol.

Protocol:
    set_char <slot 0-7> <row0> <row1> ... <row7>
    
Each row = integer 0-31 (5 pixels, bit4=col0, bit0=col4)

Display:
    widget_set <screen> <widget> <x> <y> {<chr(slot)>}
"""
import socket
import time

HOST = "127.0.0.1"
PORT = 13666

# All 8 CGRAM slots (set once at startup)
CGRAM = [
    ("BAR1",    "16 16 16 16 16 16 16 16"),   # █░░░░
    ("BAR2",    "24 24 24 24 24 24 24 24"),   # ██░░░
    ("BAR3",    "28 28 28 28 28 28 28 28"),   # ███░░
    ("BAR4",    "30 30 30 30 30 30 30 30"),   # ████░
    ("THERMO",  "4 4 4 4 14 14 31 14"),       # thermometer
    ("FAN",     "10 4 10 0 0 0 0 0"),         # fan blades
    ("NET",     "17 10 4 21 4 10 17 0"),      # network diamond
    ("SPARE",   "0 0 0 0 0 0 0 0"),           # empty/reserved
]


def lcd_cmd(s, cmd):
    """Send command to LCDd, return response."""
    s.sendall((cmd + "\n").encode())
    time.sleep(0.1)
    try:
        return s.recv(1024).decode().strip()
    except socket.timeout:
        return ""


def setup_cgram(s):
    """Upload all 8 CGRAM glyphs. Call once at startup."""
    for slot, (name, rows) in enumerate(CGRAM):
        r = lcd_cmd(s, f"set_char {slot} {rows}")
        print(f"  slot {slot} {name:10s} -> {r}")


def display_bar(s, pct):
    """Display storage bar: full cells + partial + percentage.
    
    pct: 0-100
    
    Example outputs:
        0%   -> "░░░░░░ 0%"
        25%  -> "█░░░░░ 25%"
        50%  -> "███░░░ 50%"
        100% -> "████░░ 100%"
    """
    # 7 cells wide, each cell = ~14%
    # Slots: 0=BAR1, 1=BAR2, 2=BAR3, 3=BAR4, E=BLOCK_FILLED (built-in)
    full_cells = pct // 14
    remainder = pct % 14
    
    bar = ""
    for i in range(7):
        if i < full_cells:
            bar += chr(4)  # BLOCK_FILLED (LCDd built-in)
        elif i == full_cells:
            if remainder < 4:
                bar += chr(0)   # BAR1 (1/5)
            elif remainder < 8:
                bar += chr(1)   # BAR2 (2/5)
            elif remainder < 11:
                bar += chr(2)   # BAR3 (3/5)
            else:
                bar += chr(3)   # BAR4 (4/5)
        else:
            bar += "_"          # empty cell
    
    lcd_cmd(s, f"widget_set S L1 1 1 {{STO {bar}}}")
    lcd_cmd(s, f"widget_set S L2 1 2 {{{pct}% USED}}")


def display_temp(s, temp_c):
    """Display temperature with thermometer icon."""
    lcd_cmd(s, f"widget_set S L1 1 1 {{THERMO}}")
    lcd_cmd(s, f"widget_set S L2 1 2 {{{temp_c}C}}")


def display_fan(s, rpm, pct):
    """Display fan status."""
    lcd_cmd(s, f"widget_set S L1 1 1 {{FAN}}")
    lcd_cmd(s, f"widget_set S L2 1 2 {{{rpm}RPM {pct}%}}")


# --- Demo ---
def demo():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect((HOST, PORT))
    
    lcd_cmd(s, "hello")
    lcd_cmd(s, "client_set -name demo")
    lcd_cmd(s, "screen_add S")
    lcd_cmd(s, "screen_set S -priority alert")
    lcd_cmd(s, "widget_add S L1 string")
    lcd_cmd(s, "widget_add S L2 string")
    lcd_cmd(s, "widget_add S ico icon")
    
    # Step 1: Upload CGRAM
    print("Setting up CGRAM...")
    setup_cgram(s)
    
    # Step 2: Show bars
    print("Displaying bars...")
    for pct in [0, 10, 25, 50, 75, 100]:
        display_bar(s, pct)
        time.sleep(1.5)
    
    # Step 3: Show temp
    display_temp(s, 42)
    time.sleep(2)
    
    # Step 4: Show fan
    display_fan(s, 1200, 35)
    time.sleep(2)
    
    s.close()
    print("Done")


if __name__ == "__main__":
    demo()
