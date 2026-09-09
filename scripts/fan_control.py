#!/usr/bin/env python3
import time

FAN_PWM_PATH = "/sys/class/hwmon/hwmon1/pwm2"
FAN_MIN = 10
FAN_MAX = 255
FAN_STEP = 2
FAN_INTERVAL = 5

CORE_TARGET = 45
CORE_HARD_LIMIT = 60


def get_core_temp():
    try:
        return int(open("/sys/class/hwmon/hwmon0/temp2_input").read().strip()) // 1000
    except (IOError, ValueError):
        return 0


def set_pwm(val):
    try:
        val = max(FAN_MIN, min(FAN_MAX, val))
        with open(FAN_PWM_PATH, "w") as f:
            f.write(str(val))
    except IOError:
        pass


def get_pwm():
    try:
        return int(open(FAN_PWM_PATH).read().strip())
    except (IOError, ValueError):
        return FAN_MIN


def main():
    while True:
        try:
            core = get_core_temp()
            pwm = get_pwm()

            if core > CORE_HARD_LIMIT:
                pwm = min(FAN_MAX, pwm + FAN_STEP * 4)
            elif core > CORE_TARGET:
                pwm = min(FAN_MAX, pwm + FAN_STEP)
            elif core < CORE_TARGET - 5:
                pwm = max(FAN_MIN, pwm - FAN_STEP)

            set_pwm(pwm)
        except Exception:
            pass
        time.sleep(FAN_INTERVAL)


if __name__ == "__main__":
    main()
