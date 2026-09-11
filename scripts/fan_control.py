#!/usr/bin/env python3
import subprocess
import time

FAN_PWM_PATH = "/sys/class/hwmon/hwmon1/pwm2"
FAN_ENABLE_PATH = "/sys/class/hwmon/hwmon1/pwm2_enable"
FAN_MIN = 14
FAN_MAX = 255
FAN_STEP = 2
FAN_INTERVAL = 5
CORE_TARGET = 45
CORE_HARD_LIMIT = 60
CORE_IDLE = 35
DISK_TARGET = 44
DISK_HARD_LIMIT = 50
DISK_IDLE = 40
DISK_DEVICES = ["/dev/sda", "/dev/sdb", "/dev/sdd", "/dev/sde", "/dev/sdf"]

def read_sys(path):
    try:
        return int(open(path).read().strip())
    except (IOError, ValueError):
        return None

def get_core_temp():
    v = read_sys("/sys/class/hwmon/hwmon0/temp2_input")
    return v // 1000 if v is not None else 0

def get_disk_max_temp():
    temps = []
    for dev in DISK_DEVICES:
        try:
            out = subprocess.run(
                ["smartctl", "-A", dev],
                capture_output=True, text=True, timeout=2
            ).stdout
            for line in out.splitlines():
                if line.startswith("194 ") and "Temperature" in line:
                    parts = line.split()
                    try:
                        temps.append(int(parts[9]))
                    except (IndexError, ValueError):
                        pass
                    break
        except (subprocess.TimeoutExpired, OSError):
            pass
    return max(temps) if temps else 0

def set_pwm(val):
    try:
        val = max(FAN_MIN, min(FAN_MAX, val))
        with open(FAN_PWM_PATH, "w") as f:
            f.write(str(val))
    except IOError:
        pass

def get_pwm():
    v = read_sys(FAN_PWM_PATH)
    return v if v is not None else FAN_MIN

def ensure_manual_mode():
    enable_val = read_sys(FAN_ENABLE_PATH)
    if enable_val is None or enable_val != 1:
        try:
            with open(FAN_ENABLE_PATH, "w") as f:
                f.write("1")
        except IOError:
            pass

def main():
    while True:
        try:
            ensure_manual_mode()
            core = get_core_temp()
            disk = get_disk_max_temp()
            pwm = get_pwm()

            cpu_hot = core > CORE_HARD_LIMIT or disk > DISK_HARD_LIMIT
            cpu_warm = core > CORE_TARGET or disk > DISK_TARGET
            cpu_cold = core < CORE_IDLE and disk < DISK_IDLE

            if cpu_hot:
                pwm = min(FAN_MAX, pwm + FAN_STEP * 4)
            elif cpu_warm:
                pwm = min(FAN_MAX, pwm + FAN_STEP)
            elif cpu_cold:
                pwm = max(FAN_MIN, pwm - FAN_STEP)

            set_pwm(pwm)
        except Exception:
            pass
        time.sleep(FAN_INTERVAL)

if __name__ == "__main__":
    main()
