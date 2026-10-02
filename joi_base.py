"""
joi_base.py — shared helpers for JOI 2.0 offline tool modules.

Built primarily on os/sys so every tool module can detect platform, resolve
paths, and read config without pulling in extra dependencies. This keeps the
whole toolkit importable and runnable on a machine with zero network access
and only the Python standard library installed.
"""
import os
import sys
import json

# ── Platform detection (sys, not platform module) ───────────────────────────
# sys.platform values: "win32", "darwin", "linux", "linux2" (old 2.x)
_RAW_PLATFORM = sys.platform

def get_os() -> str:
    """Returns 'windows' | 'mac' | 'linux'."""
    if _RAW_PLATFORM.startswith("win"):
        return "windows"
    if _RAW_PLATFORM == "darwin":
        return "mac"
    return "linux"

def is_windows() -> bool: return get_os() == "windows"
def is_mac() -> bool:     return get_os() == "mac"
def is_linux() -> bool:   return get_os() == "linux"


# ── Base directory / frozen-executable handling (os + sys only) ────────────
def base_dir() -> str:
    """
    Root directory of the running JOI installation.
    Mirrors the _base_dir() pattern from the reference project, but uses
    os.path instead of pathlib so it stays inside os/sys.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # this file is expected to live at <joi_root>/core/joi_base.py
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def config_dir() -> str:
    path = os.path.join(base_dir(), "config")
    os.makedirs(path, exist_ok=True)
    return path


def config_path(filename: str = "settings.json") -> str:
    return os.path.join(config_dir(), filename)


def load_config(filename: str = "settings.json") -> dict:
    path = config_path(filename)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[joi_base] \u26a0\ufe0f Could not read config {filename}: {e}")
        return {}


def save_config(data: dict, filename: str = "settings.json") -> bool:
    path = config_path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[joi_base] \u26a0\ufe0f Could not write config {filename}: {e}")
        return False


# ── PATH lookup without shutil (os + sys only) ──────────────────────────────
def which(binary_name: str) -> str | None:
    """
    Minimal reimplementation of shutil.which using only os.
    Looks up binary_name on PATH, respecting PATHEXT on Windows.
    """
    path_env = os.environ.get("PATH", "")
    if not path_env:
        return None

    exts = [""]
    if is_windows():
        pathext = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD")
        exts = pathext.split(os.pathsep)

    for directory in path_env.split(os.pathsep):
        if not directory:
            continue
        for ext in exts:
            candidate = os.path.join(directory, binary_name + ext)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


# ── Connectivity check (os only — no requests/socket dependency) ───────────
def is_online(timeout: float = 1.5) -> bool:
    """
    Cheap offline/online check using only the standard library's socket
    module (imported lazily so importing joi_base never requires network
    libraries to exist). Returns False fast when there's no connection,
    so callers can branch to fully local behavior.
    """
    import socket
    try:
        socket.setdefaulttimeout(timeout)
        # DNS root-ish probe: a well-known resolver, port 53 (DNS), no data sent
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 53))
        return True
    except OSError:
        return False


# ── Logging helper shared across tool modules ───────────────────────────────
def log(module: str, message: str) -> None:
    print(f"[{module}] {message}")