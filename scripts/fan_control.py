#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subprocess
import time
from datetime import datetime
from smart_monitor import get_all_disk_data, get_fallback_disk_info
from fan_config import load as _load_config

_CFG = _load_config()

FAN_PWM_PATH = "/sys/class/hwmon/hwmon1/pwm2"
FAN_ENABLE_PATH = "/sys/class/hwmon/hwmon1/pwm2_enable"
FAN_MIN = _CFG["FAN_MIN"]
FAN_MAX = _CFG["FAN_MAX"]
FAN_MAX_CAP = _CFG["FAN_MAX_CAP"]
START_PWM = _CFG["START_PWM"]
FAN_INTERVAL = _CFG["FAN_INTERVAL"]
DISK_DEVICES = ["/dev/sda", "/dev/sdb", "/dev/sdd", "/dev/sde", "/dev/sdf"]

CORE_IDLE = _CFG["CORE_IDLE"]
CORE_TARGET = _CFG["CORE_TARGET"]
CORE_CRITICAL = _CFG["CORE_CRITICAL"]
DISK_TARGET = _CFG["DISK_TARGET"]
DISK_HARD_LIMIT = _CFG["DISK_HARD_LIMIT"]
DISK_RAMP_START = _CFG["DISK_RAMP_START"]
DISK_RAMP_STEP = _CFG["DISK_RAMP_STEP"]

PWM_SEARCH_STEP = 5
PWM_STABLE_THRESHOLD = _CFG["PWM_STABLE_THRESHOLD"]
DECREASE_STEP = _CFG["DECREASE_STEP"]
DEADBAND_HIGH = _CFG["DEADBAND_HIGH"]
LEARN_FLOOR_BOOST = _CFG["LEARN_FLOOR_BOOST"]
MIN_STABILIZE_SECONDS = _CFG["MIN_STABILIZE_SECONDS"]
OBSERVATION_WINDOW = _CFG["OBSERVATION_WINDOW"]
PROBE_INTERVAL = _CFG["PROBE_INTERVAL"]

UNLOCK_THRESHOLD = _CFG["UNLOCK_THRESHOLD"]

UNLOCK_THRESHOLD = _CFG["UNLOCK_THRESHOLD"]

_stable_pwm = None
_last_temp = 0
_last_change_time = 0
_last_action = "idle"
_pwm_floor = _CFG["PWM_FLOOR"] if _CFG["PWM_FLOOR"] > 0 else FAN_MIN
_candidate_pwm = None
_candidate_start = 0
_candidate_min_temp = 999
_candidate_max_temp = 0
_probe_due_at = 0
_tuning_locked = False

def read_sys(path):
    try:
        return int(open(path).read().strip())
    except (IOError, ValueError):
        return None

def get_core_temp():
    v = read_sys("/sys/class/hwmon/hwmon0/temp2_input")
    return v // 1000 if v is not None else 0

def get_disk_info():
    try:
        data = get_all_disk_data(DISK_DEVICES)
        if not data:
            return get_fallback_disk_info()
        hottest = max(data.values(), key=lambda d: d["temp"])
        hottest["alerts_all"] = []
        for dev, d in data.items():
            for a in d["alerts"]:
                hottest["alerts_all"].append(a)
        return hottest
    except Exception as e:
        print(f"get_disk_info error: {e}", flush=True)
        return get_fallback_disk_info()

def _start_candidate(pwm, now):
    global _candidate_pwm, _candidate_start, _candidate_min_temp
    global _candidate_max_temp, _probe_due_at
    _candidate_pwm = pwm
    _candidate_start = now
    _candidate_min_temp = 999
    _candidate_max_temp = 0
    _probe_due_at = now + PROBE_INTERVAL

def _observe_candidate(disk_temp, now):
    global _candidate_min_temp, _candidate_max_temp
    if disk_temp < _candidate_min_temp:
        _candidate_min_temp = disk_temp
    if disk_temp > _candidate_max_temp:
        _candidate_max_temp = disk_temp

def _candidate_passed(now, disk_temp):
    required_window = 300 if disk_temp < DISK_RAMP_START else OBSERVATION_WINDOW
    return (now - _candidate_start) >= required_window

def _candidate_failed():
    return _candidate_max_temp > DISK_TARGET

def compute_pwm(core_temp, disk_info, current_pwm):
    global _stable_pwm, _last_temp, _last_change_time, _last_action, _pwm_floor
    global _candidate_pwm, _candidate_start, _candidate_min_temp, _candidate_max_temp
    global _probe_due_at, _tuning_locked
    disk_temp = disk_info["temp"] if disk_info["temp"] > 0 else DISK_TARGET
    now = time.time()

    if core_temp > CORE_CRITICAL or disk_temp > DISK_HARD_LIMIT:
        _stable_pwm = None
        _last_change_time = now
        _last_action = "emergency"
        _tuning_locked = False
        _candidate_pwm = None
        return FAN_MAX

    if _stable_pwm is None:
        start_pwm = max(_pwm_floor, min(FAN_MAX_CAP, START_PWM))
        _stable_pwm = start_pwm
        _last_change_time = now
        _last_action = "init"
        _start_candidate(start_pwm, now)
        return _stable_pwm

    if _candidate_pwm is None:
        _start_candidate(_stable_pwm, now)

    _observe_candidate(disk_temp, now)

    if _candidate_pwm is not None and _candidate_failed() and not _tuning_locked:
        _pwm_floor = min(FAN_MAX_CAP, _stable_pwm + LEARN_FLOOR_BOOST)
        _tuning_locked = True

    if disk_temp >= DISK_HARD_LIMIT:
        _stable_pwm = FAN_MAX
        _last_change_time = now
        _last_action = "critical"
        return FAN_MAX

    if disk_temp > DISK_TARGET + DEADBAND_HIGH and disk_temp < DISK_HARD_LIMIT:
        new_pwm = min(FAN_MAX_CAP, _stable_pwm + PWM_SEARCH_STEP)
        if new_pwm != _stable_pwm:
            _stable_pwm = new_pwm
            _last_change_time = now
            _last_action = "increase"
            _start_candidate(_stable_pwm, now)
        _last_temp = disk_temp
        return _stable_pwm

    if _tuning_locked:
        if (disk_temp < DISK_TARGET - UNLOCK_THRESHOLD
                and (now - _last_change_time) >= MIN_STABILIZE_SECONDS):
            _tuning_locked = False
            _pwm_floor = max(FAN_MIN, _stable_pwm - LEARN_FLOOR_BOOST)
            _start_candidate(_stable_pwm, now)
            _last_change_time = now
            _last_action = "unlock"
        _last_temp = disk_temp
        return _stable_pwm

    if _candidate_passed(now, disk_temp) and not _candidate_failed():
        next_pwm = max(_pwm_floor, _stable_pwm - DECREASE_STEP)
        if next_pwm != _stable_pwm and now >= _probe_due_at:
            _stable_pwm = next_pwm
            _last_change_time = now
            _last_action = "decrease"
            _start_candidate(_stable_pwm, now)

    _last_temp = disk_temp
    return _stable_pwm

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

def log_alerts(alerts):
    if not alerts:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for alert in alerts:
        print(f"[{ts}] {alert}", flush=True)

def main():
    print("fan_control.py: starting main loop", flush=True)
    iteration = 0
    while True:
        iteration += 1
        try:
            ensure_manual_mode()
            core = get_core_temp()
            disk = get_disk_info()
            pwm = get_pwm()
            pwm = compute_pwm(core, disk, pwm)
            set_pwm(pwm)
            log_alerts(disk.get("alerts_all", []))
            if iteration % 6 == 0:
                print(f"iter={iteration} core={core}C disk={disk["temp"]}C pwm={pwm} stable={_stable_pwm}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)
        time.sleep(FAN_INTERVAL)

if __name__ == "__main__":
    main()
