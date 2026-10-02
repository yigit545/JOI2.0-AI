"""
system_monitor.py — JOI 2.0 offline system monitor.

Built primarily on os/sys so it works with zero third-party dependencies:
  - Linux : reads /proc/meminfo, /proc/loadavg, /proc/stat directly (os.open/
            os.read or plain file I/O — no /proc parsing library needed)
  - all   : os.cpu_count(), os.getloadavg() where available
  - optional richer stats (per-core %, temps) via psutil if it happens to be
    installed, but the module is fully functional without it.

Call signature matches JOI's existing tool modules:
    system_monitor(parameters, response=None, player=None, session_memory=None)
"""
import os
import sys
import time

from joi_base import get_os, is_linux, is_windows, is_mac, log

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


DEFAULT_THRESHOLDS = {"cpu": 90.0, "ram": 90.0}
_COOLDOWN = 300


# ── RAM (Linux: /proc/meminfo via plain file I/O — os module only) ─────────
def _ram_linux() -> dict | None:
    try:
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key.strip()] = int(rest.strip().split()[0])  # kB
        total_kb = info.get("MemTotal", 0)
        avail_kb = info.get("MemAvailable", info.get("MemFree", 0))
        used_kb = total_kb - avail_kb
        if total_kb == 0:
            return None
        return {
            "ram_total_gb": round(total_kb / 1024 ** 2, 1),
            "ram_used_gb": round(used_kb / 1024 ** 2, 1),
            "ram_percent": round(used_kb / total_kb * 100, 1),
        }
    except Exception as e:
        log("SystemMonitor", f"\u26a0\ufe0f /proc/meminfo read failed: {e}")
        return None


def _ram_fallback() -> dict | None:
    """Cross-platform fallback via psutil, only used if it's installed."""
    if not _PSUTIL:
        return None
    vm = psutil.virtual_memory()
    return {
        "ram_total_gb": round(vm.total / 1024 ** 3, 1),
        "ram_used_gb": round(vm.used / 1024 ** 3, 1),
        "ram_percent": round(vm.percent, 1),
    }


def _get_ram() -> dict:
    if is_linux():
        result = _ram_linux()
        if result:
            return result
    result = _ram_fallback()
    return result or {"ram_total_gb": None, "ram_used_gb": None, "ram_percent": None}


# ── CPU load (os.getloadavg on POSIX; /proc/stat delta on Linux for %) ─────
_last_cpu_sample: tuple[float, float] | None = None  # (idle, total)


def _cpu_percent_linux() -> float | None:
    """
    Instantaneous-ish CPU percent from two /proc/stat reads.
    Uses only os/plain file I/O — no psutil needed.
    """
    global _last_cpu_sample
    try:
        def _read_stat():
            with open("/proc/stat", "r") as f:
                parts = f.readline().split()[1:]
            nums = list(map(int, parts))
            idle = nums[3] + nums[4]  # idle + iowait
            total = sum(nums)
            return idle, total

        idle1, total1 = _read_stat()
        if _last_cpu_sample is None:
            time.sleep(0.15)
            idle2, total2 = _read_stat()
        else:
            idle2, total2 = idle1, total1
            idle1, total1 = _last_cpu_sample

        _last_cpu_sample = (idle2, total2)

        d_idle = idle2 - idle1
        d_total = total2 - total1
        if d_total <= 0:
            return None
        return round((1 - d_idle / d_total) * 100, 1)
    except Exception as e:
        log("SystemMonitor", f"\u26a0\ufe0f /proc/stat read failed: {e}")
        return None


def _get_cpu_percent() -> float | None:
    if is_linux():
        result = _cpu_percent_linux()
        if result is not None:
            return result
    if _PSUTIL:
        return round(psutil.cpu_percent(interval=0.2), 1)
    # Last-resort: load average relative to core count (POSIX only)
    try:
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 1
        return round(min(load1 / cores * 100, 100.0), 1)
    except (AttributeError, OSError):
        return None


# ── Disk (os.statvfs on POSIX; psutil fallback on Windows) ──────────────────
def _get_disk(path: str = "/") -> dict:
    try:
        if hasattr(os, "statvfs"):
            st = os.statvfs(path)
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            used = total - free
            return {
                "disk_total_gb": round(total / 1024 ** 3, 1),
                "disk_used_gb": round(used / 1024 ** 3, 1),
                "disk_percent": round(used / total * 100, 1) if total else None,
            }
    except Exception as e:
        log("SystemMonitor", f"\u26a0\ufe0f statvfs failed: {e}")

    if _PSUTIL:
        du = psutil.disk_usage(path if not is_windows() else "C:\\")
        return {
            "disk_total_gb": round(du.total / 1024 ** 3, 1),
            "disk_used_gb": round(du.used / 1024 ** 3, 1),
            "disk_percent": round(du.percent, 1),
        }
    return {"disk_total_gb": None, "disk_used_gb": None, "disk_percent": None}


# ── Uptime (Linux: /proc/uptime; fallback: unavailable without psutil) ─────
def _get_uptime() -> str:
    if is_linux():
        try:
            with open("/proc/uptime", "r") as f:
                secs = float(f.readline().split()[0])
            h, m = int(secs // 3600), int((secs % 3600) // 60)
            return f"{h}h {m}m"
        except Exception:
            pass
    if _PSUTIL:
        secs = time.time() - psutil.boot_time()
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        return f"{h}h {m}m"
    return "unknown"


def get_system_status() -> dict:
    """Snapshot of current system metrics — no network, no subprocess calls."""
    status = {
        "os": get_os(),
        "cpu_percent": _get_cpu_percent(),
        "cpu_count": os.cpu_count(),
        "uptime": _get_uptime(),
    }
    status.update(_get_ram())
    status.update(_get_disk())
    return status


class SystemMonitor:
    """Stateful monitor — cooldown persists across checks within a session."""

    def __init__(self, thresholds: dict | None = None):
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._last_alert: dict[str, float] = {}

    def _can_alert(self, key: str) -> bool:
        return (time.monotonic() - self._last_alert.get(key, 0)) > _COOLDOWN

    def _record(self, key: str) -> None:
        self._last_alert[key] = time.monotonic()

    def check(self) -> str | None:
        cpu = _get_cpu_percent()
        ram = _get_ram().get("ram_percent")
        alerts = []

        if cpu is not None and cpu >= self.thresholds["cpu"] and self._can_alert("cpu"):
            alerts.append(f"[SYSTEM_ALERT] CPU usage is at {cpu:.0f}% \u2014 warn the user and suggest closing heavy applications.")
            self._record("cpu")

        if ram is not None and ram >= self.thresholds["ram"] and self._can_alert("ram"):
            alerts.append(f"[SYSTEM_ALERT] RAM is at {ram:.0f}% \u2014 nearly exhausted. Warn the user and suggest freeing memory.")
            self._record("ram")

        return " ".join(alerts) if alerts else None


# ── Public tool entry point (matches JOI's existing tool signature) ────────
def system_monitor(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "status").lower().strip()

    if player:
        player.write_log(f"[SystemMonitor] {action}")

    try:
        if action == "status":
            s = get_system_status()
            lines = [
                f"OS: {s['os']}  |  CPU cores: {s['cpu_count']}  |  Uptime: {s['uptime']}",
                f"CPU: {s['cpu_percent']}%" if s['cpu_percent'] is not None else "CPU: unavailable",
                f"RAM: {s['ram_used_gb']}/{s['ram_total_gb']} GB ({s['ram_percent']}%)"
                if s['ram_percent'] is not None else "RAM: unavailable",
                f"Disk: {s['disk_used_gb']}/{s['disk_total_gb']} GB ({s['disk_percent']}%)"
                if s['disk_percent'] is not None else "Disk: unavailable",
            ]
            return "\n".join(lines)

        return f"Unknown system_monitor action: '{action}'. Available: status."

    except Exception as e:
        log("SystemMonitor", f"\u274c {action} failed: {e}")
        return f"system_monitor '{action}' failed: {e}"