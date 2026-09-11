#!/usr/bin/env python3
import socket
import time

WIDTH = 16
HEIGHT = 2
LCD_HOST = "127.0.0.1"
LCD_PORT = 13666

class LCD:
    def __init__(self):
        self.s = socket.create_connection((LCD_HOST, LCD_PORT), timeout=5)
        self._send("hello")
        self._send("client_set -name lcd-lab")
        self._send("screen_add test")
        self._send("screen_set test -priority alert")
        self._send("widget_add test l1 string")
        self._send("widget_add test l2 string")
    
    def _send(self, cmd):
        self.s.sendall((cmd + "\n").encode())
    
    def clear(self):
        self._send("widget_set test l1 1 1 \"                \"")
        self._send("widget_set test l2 1 2 \"                \"")
    
    def write(self, x, y, text):
        line = f"widget_set test l{y+1} {x+1} {y+1} \"{text}\""
        self._send(line)
    
    def write_raw(self, x, y, data):
        chars = "".join(chr(b) for b in data)
        self.write(x, y, chars)
    
    def create_char(self, slot, pattern):
        bits = "".join("{:05b}".format(p) for p in pattern)
        self._send(f"widget_add test c{slot} char")
        self._send(f"widget_set test c{slot} {bits}")

def test_basic_text(lcd):
    lcd.clear()
    lcd.write(0, 0, "DX4000 LCD LAB")
    lcd.write(0, 1, "BASIC TEXT OK")
    print("TEST 1: Basic text")

def test_positioning(lcd):
    for x in range(WIDTH):
        lcd.clear()
        lcd.write(x, 0, "X")
        lcd.write(x, 1, str(x))
        time.sleep(0.25)
    print("TEST 2: Positioning")

def test_two_line(lcd):
    lcd.clear()
    for x in range(WIDTH):
        lcd.write(x, 0, "A")
        lcd.write(WIDTH - x - 1, 1, "B")
        time.sleep(0.15)
    print("TEST 10: Two-line")

def test_ascii(lcd):
    for start in range(32, 127, WIDTH):
        chars = "".join(chr(code) for code in range(start, min(start + WIDTH, 127)))
        lcd.clear()
        lcd.write(0, 0, chars[:WIDTH])
        lcd.write(0, 1, f"ASCII {start}")
        time.sleep(0.5)
    print("TEST 5: ASCII")

def test_cgram(lcd):
    patterns = [[0b00100, 0b01110, 0b11111, 0b00100, 0b00100, 0b00000, 0b00100, 0b00000]]
    for slot, pattern in enumerate(patterns[:1]):
        lcd.create_char(slot, pattern)
    lcd.clear()
    lcd.write_raw(0, 0, bytes([0]))
    lcd.write(0, 1, "CGRAM SLOT 0")
    print("TEST 7: CGRAM")

def main():
    print("DX4000 LCD LAB - AUTO")
    try:
        lcd = LCD()
        time.sleep(0.5)
        
        test_basic_text(lcd)
        time.sleep(3)
        
        test_positioning(lcd)
        time.sleep(3)
        
        test_two_line(lcd)
        time.sleep(3)
        
        test_ascii(lcd)
        time.sleep(3)
        
        test_cgram(lcd)
        time.sleep(3)
        
        lcd.clear()
        lcd.write(0, 0, "TESTS COMPLETE")
        lcd.write(0, 1, "CHECK LCD NOW")
        print("DONE")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()
