# HD44780 CGRAM Icon Specification

## Hardware

- Display: 16x2 characters, HD44780-compatible
- Controller: HD44780 (or compatible)
- Communication: LCDd via TCP socket (set_char protocol)

## CGRAM Constraints

### Grid Size
Each custom character is a **5 wide x 8 tall** pixel grid.

```
  Col 0  1  2  3  4
Row 0:  .  .  .  .  .
Row 1:  .  .  .  .  .
Row 2:  .  .  .  .  .
Row 3:  .  .  .  .  .
Row 4:  .  .  .  .  .
Row 5:  .  .  .  .  .
Row 6:  .  .  .  .  .
Row 7:  .  .  .  .  .
```

### Pixel Encoding

Each row is an integer **0-31** (5 bits).

```
Bit:  4  3  2  1  0
Col:  0  1  2  3  4
```

Examples:
- `31` = `11111` = all 5 pixels ON (full block)
- `0`  = `00000` = all 5 pixels OFF (empty)
- `16` = `10000` = only column 0 ON (left vertical line)
- `4`  = `00100` = only column 2 ON (center dot)

### Row 7 Reserved
Row 7 is used as the descender line (for letters like g, j, p, q, y).
**Avoid placing pixels on Row 7** unless intentional.

### Max Slots
**8 custom characters** (slots 0-7) available.

## LCDd Protocol

```python
# Upload glyph to slot N
s.sendall(f"set_char {N} {row0} {row1} ... {row7}\n")

# Display slot N in text
s.sendall(f"widget_set screen line 1 1 {{{chr(N)}}}\n")
```

## Current Glyphs (to be refined)

| Slot | Name    | Rows (8 values, 0-31 each) |
|------|---------|---------------------------|
| 0    | DOWN ↓  | 4 4 4 4 14 4 0 0          |
| 1    | UP ↑    | 4 4 4 14 4 4 4 0          |
| 2    | DISK ▣  | 14 31 17 21 17 31 14 0    |
| 3    | TEMP ℃  | 4 4 4 4 14 14 31 14       |
| 4    | FAN ⟳   | 20 12 31 6 5 0 0 0        |
| 5    | OK ✓    | 1 3 6 12 24 8 0 0         |
| 6    | ALERT ⚠ | 4 14 14 14 4 0 4 0        |
| 7    | ACT ⚡   | 0 4 12 31 6 4 0 0         |

## Design Rules

1. **Contrast is key** - Use bold, simple shapes. Fine details get lost at 5x8.
2. **Center important elements** on columns 1-3 (columns 0 and 4 are edge pixels).
3. **Leave Row 7 empty** unless designing a specific descender.
4. **Test at actual size** - Print at 5x8mm and hold up to screen.
5. **Avoid sub-pixel alignment** - Each pixel is either ON or OFF.

## Test Script

```bash
ssh root@10.10.10.101 "python3 /opt/dx4000-lcd/test_cgram_icons.py"
```

## Reference: ASCII Art Templates

```
DOWN (↓)          UP (↑)            DISK (▣)         TEMP (℃)
. . X . .         . . X . .         . X X X .         . . X . .
. . X . .         . X X X .         X X X X X         . . X . .
. . X . .         X . X . X         X . . . X         . . X . .
. . X . .         . . X . .         X . X . X         . . X . .
X . X . X         . . X . .         X . . . X         . X X X .
. X X X .         . . X . .         X X X X X         . X X X .
. . X . .         . . X . .         . X X X .         X X X X X
. . . . .         . . . . .         . . . . .         . X X X .

FAN (⟳)           OK (✓)            ALERT (⚠)        ACT (⚡)
. X . X .         . . . . X         . . X . .         . . . . .
. . X . .         . . . X X         . X X X .         . . X . .
X X X X X         . . X X .         . X X X .         . X X . .
. . X X .         . X X . .         . X X X .         X X X X X
. . X . X         X X . . .         . . X . .         . . X X .
. . . . .         . X . . .         . . . . .         . . X . .
. . . . .         . . . . .         . . X . .         . . . . .
. . . . .         . . . . .         . . . . .         . . . . .
```
