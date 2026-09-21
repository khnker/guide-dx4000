#!/usr/bin/env python3
"""Configuration loader for fan_control.py.
Reads /etc/dx4000/fan_control.conf and exposes constants.
Falls back to defaults if file is missing or malformed.
"""
import os
import sys

CONFIG_PATH = "/etc/dx4000/fan_control.conf"

DEFAULTS = {
    "FAN_MIN": 14,
    "FAN_MAX": 255,
    "FAN_MAX_CAP": 178,
    "START_PWM": 70,
    "CORE_IDLE": 35,
    "CORE_TARGET": 45,
    "CORE_CRITICAL": 60,
    "DISK_TARGET": 45,
    "DISK_HARD_LIMIT": 50,
    "DISK_RAMP_START": 42,
    "DISK_RAMP_STEP": 2,
    "PWM_FLOOR": 0,
    "PWM_STABLE_THRESHOLD": 3,
    "DECREASE_STEP": 3,
    "DEADBAND_HIGH": 1,
    "LEARN_FLOOR_BOOST": 5,
    "MIN_STABILIZE_SECONDS": 45,
    "OBSERVATION_WINDOW": 5400,
    "PROBE_INTERVAL": 900,
    "UNLOCK_THRESHOLD": 3,
    "FAN_INTERVAL": 5,
}


def load(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    if not os.path.exists(path):
        return cfg
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.split("#")[0].strip()
                if key in DEFAULTS:
                    try:
                        cfg[key] = int(val)
                    except ValueError:
                        pass
    except (IOError, OSError):
        pass
    return cfg


if __name__ == "__main__":
    cfg = load()
    for k, v in cfg.items():
        print(f"{k} = {v}")
