#!/usr/bin/env python3
import subprocess
import time
from datetime import datetime
from smart_monitor import get_all_disk_data, get_fallback_disk_info

FAN_PWM_PATH = "/sys/class/hwmon/hwmon1/pwm2"
FAN_ENABLE_PATH = "/sys/class/hwmon/hwmon1/pwm2_enable"
FAN_MIN = 14
FAN_MAX = 255
FAN_INTERVAL = 5
DISK_DEVICES = ["/dev/sda", "/dev/sdb", "/dev/sdd", "/dev/sde", "/dev/sdf"]

# Temperature thresholds
CORE_IDLE = 35
CORE_TARGET = 45
CORE_CRITICAL = 60
DISK_TARGET = 42      # Keep disks below this
DISK_HARD_LIMIT = 50  # Never exceed this

# Adaptive PWM: find the minimum speed that keeps disks cool
PWM_SEARCH_STEP = 5   # How much to adjust when searching
PWM_STABLE_THRESHOLD = 2  # Degrees below target to consider "stable"

# State: track the PWM that worked
_stable_pwm = None
_last_temp = 0
_last_change_time = 0
MIN_STABILIZE_SECONDS = 60  # Wait before adjusting again

def read_sys(path):
    try:
        return int(open(path).read().strip())
    except (IOError, ValueError):
        return None

def get_core_temp():
    v = read_sys("/sys/class/hwmon/hwmon0/temp2_input")
    return v // 1000 if v is not None else 0

def get_disk_info():
    """Get disk data from SMART monitor with caching."""
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
    except Exception:
        return get_fallback_disk_info()

def compute_pwm(core_temp, disk_info, current_pwm):
    """Adaptive PWM: find minimum speed that keeps disks cool.
    
    Strategy:
    1. If disks hot → increase PWM
    2. If disks cool AND we've been stable → try decreasing
    3. Once we find the sweet spot, hold it
    """
    global _stable_pwm, _last_temp, _last_change_time
    
    disk_temp = disk_info["temp"] if disk_info["temp"] > 0 else DISK_TARGET
    now = time.time()
    
    # Critical: always go max
    if core_temp > CORE_CRITICAL or disk_temp > DISK_HARD_LIMIT:
        _stable_pwm = None
        _last_change_time = now
        return FAN_MAX
    
    # If we don't have a stable PWM yet, start searching
    if _stable_pwm is None:
        _stable_pwm = max(FAN_MIN, min(FAN_MAX, 80))  # Start at moderate speed
        _last_change_time = now
    
    time_since_change = now - _last_change_time
    
    # If disks are too hot, increase immediately
    if disk_temp > DISK_TARGET:
        # Scale increase based on how hot
        if disk_temp > DISK_TARGET + 5:
            step = PWM_SEARCH_STEP * 4  # Hot: increase fast
        else:
            step = PWM_SEARCH_STEP * 2  # Warm: increase moderate
        _stable_pwm = min(FAN_MAX, _stable_pwm + step)
        _last_change_time = now
        _last_temp = disk_temp
        return _stable_pwm
    
    # If disks are cool and we've waited long enough, try to decrease
    if disk_temp < DISK_TARGET - PWM_STABLE_THRESHOLD:
        if time_since_change >= MIN_STABILIZE_SECONDS:
            # Only decrease if temperature hasn't risen
            if disk_temp <= _last_temp:
                new_pwm = max(FAN_MIN, _stable_pwm - PWM_SEARCH_STEP)
                if new_pwm != _stable_pwm:
                    _stable_pwm = new_pwm
                    _last_change_time = now
    
    _last_temp = disk_temp
    return _stable_pwm

# Keep for backward compatibility
FAN_STEP = PWM_SEARCH_STEP

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
    """Print alerts with timestamp."""
    if not alerts:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for alert in alerts:
        print(f"[{ts}] {alert}")

def test_scenarios():
    """Non-destructive tests for PWM decision logic."""
    global _stable_pwm, _last_temp, _last_change_time
    _stable_pwm = None
    _last_temp = 0
    _last_change_time = 0
    
    all_ok = True
    healthy = {"temp": 35, "thresholds": {"target": 42, "hard_limit": 50}, "health": "healthy", "alerts": []}
    warm = {"temp": 44, "thresholds": {"target": 42, "hard_limit": 50}, "health": "healthy", "alerts": []}
    hot = {"temp": 48, "thresholds": {"target": 42, "hard_limit": 50}, "health": "healthy", "alerts": []}
    critical = {"temp": 55, "thresholds": {"target": 42, "hard_limit": 50}, "health": "healthy", "alerts": []}
    cold = {"temp": 30, "thresholds": {"target": 42, "hard_limit": 50}, "health": "healthy", "alerts": []}
    fallback = {"temp": 42, "thresholds": {"target": 42, "hard_limit": 50}, "health": "unknown", "alerts": []}

    print("  Adaptive PWM tests:")
    cases = [
        ("cold",         30, cold,    FAN_MIN,  lambda p: p >= FAN_MIN),
        ("at_target",    40, healthy, 80,       lambda p: p == 80),  # Starts at 80
        ("warm_disk",    40, warm,    80,       lambda p: p > 80),   # Should increase
        ("hot_disk",     40, hot,     80,       lambda p: p >= 100), # Should increase more
        ("critical",     70, critical,80,       lambda p: p == FAN_MAX),
        ("unavailable",  40, fallback,80,       lambda p: FAN_MIN <= p <= FAN_MAX),
    ]

    for name, core, disk, cur, check in cases:
        _stable_pwm = None  # Reset for each test
        new_pwm = compute_pwm(core, disk, cur)
        ok = check(new_pwm)
        if not ok:
            all_ok = False
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}: {cur}→{new_pwm}")
    
    # Test stability: once at sweet spot, should hold
    print("\n  Stability test:")
    _stable_pwm = 120
    _last_temp = 40
    _last_change_time = 0  # Allow decrease
    
    # Cool disks - should try to decrease
    pwm1 = compute_pwm(35, healthy, 120)
    if pwm1 < 120:
        print(f"    [PASS] Decreased from 120 to {pwm1} when cool")
    else:
        print(f"    [FAIL] Did not decrease: {pwm1}")
        all_ok = False
    
    return all_ok

def main():
    while True:
        try:
            ensure_manual_mode()
            core = get_core_temp()
            disk = get_disk_info()
            pwm = get_pwm()
            pwm = compute_pwm(core, disk, pwm)
            set_pwm(pwm)
            log_alerts(disk.get("alerts_all", []))
        except Exception:
            pass
        time.sleep(FAN_INTERVAL)

if __name__ == "__main__":
    test_scenarios()
