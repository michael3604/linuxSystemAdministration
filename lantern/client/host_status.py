from __future__ import annotations
import os, time, json
from pathlib import Path
from typing import Dict, Any

from atomic import atomic_write_text
from timeutil import now_text


def _read_cpu():
    with open('/proc/stat', 'r', encoding='utf-8') as f:
        parts = f.readline().split()[1:]
    nums = [int(x) for x in parts]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    total = sum(nums)
    return idle, total


def cpu_percent() -> float | None:
    try:
        i1, t1 = _read_cpu(); time.sleep(0.1); i2, t2 = _read_cpu()
        total = t2 - t1; idle = i2 - i1
        if total <= 0: return None
        return round((1 - idle / total) * 100, 1)
    except Exception:
        return None


def memory_info():
    vals = {}
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8') as f:
            for line in f:
                k, v = line.split(':', 1)
                vals[k] = int(v.strip().split()[0])
        total = vals.get('MemTotal')
        avail = vals.get('MemAvailable')
        if total and avail is not None:
            used_percent = round((1 - avail / total) * 100, 1)
            return used_percent, round(avail / 1024, 1)
    except Exception:
        pass
    return None, None


def cpu_temp():
    candidates = []
    for glob in ('/sys/class/thermal/thermal_zone*/temp', '/sys/class/hwmon/hwmon*/temp*_input'):
        candidates.extend(Path('/').glob(glob.lstrip('/')))
    for path in candidates:
        try:
            raw = int(path.read_text().strip())
            c = raw / 1000 if raw > 200 else raw
            if 0 <= c <= 120:
                return round(c, 1)
        except Exception:
            continue
    return None


def write_status(config: Dict[str, Any]) -> Path:
    local = Path(config['paths']['localDataFolder'])
    maint_file = Path(config['collection'].get('maintenanceModeFile', '/run/lantern/maintenanceMode'))
    ram_percent, ram_available = memory_info()
    data = {
        'timestamp': now_text(),
        'hostName': config.get('hostName') or os.uname().nodename,
        'cpuPercent': cpu_percent(),
        'ramPercent': ram_percent,
        'ramAvailableMb': ram_available,
        'cpuTempC': cpu_temp(),
        'maintenanceMode': maint_file.exists(),
    }
    path = local / 'status.json'
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
    return path
