"""
open_app.py — JOI 2.0 offline application launcher.

Built primarily on os/sys:
  - Windows : os.startfile() — native, async, no subprocess needed
  - Linux   : os.system("<bin> >/dev/null 2>&1 &") — backgrounded via shell &
  - macOS   : os.system('open -a "<App>" &')       — 'open' is the standard
              macOS launcher; still routed through os.system, not subprocess

PATH lookup uses joi_base.which() (os-only reimplementation of shutil.which),
so the whole module has zero third-party dependencies and works fully
offline — nothing here ever touches the network.

Call signature matches JOI's existing tool modules:
    open_app(parameters, response=None, player=None, session_memory=None)
"""
import os

from joi_base import get_os, is_windows, is_mac, is_linux, which, log

# App name -> per-OS launch target. Extend freely; unknown names fall back
# to trying the raw name directly on every platform.
_APP_ALIASES: dict[str, dict[str, str]] = {
    "firefox":       {"windows": "firefox",        "mac": "Firefox",             "linux": "firefox"},
    "chrome":        {"windows": "chrome",          "mac": "Google Chrome",       "linux": "google-chrome"},
    "code":          {"windows": "code",            "mac": "Visual Studio Code",  "linux": "code"},
    "vscode":        {"windows": "code",            "mac": "Visual Studio Code",  "linux": "code"},
    "terminal":      {"windows": "wt",              "mac": "Terminal",            "linux": "x-terminal-emulator"},
    "files":         {"windows": "explorer.exe",    "mac": "Finder",              "linux": "nautilus"},
    "calculator":    {"windows": "calc.exe",        "mac": "Calculator",          "linux": "gnome-calculator"},
    "text editor":   {"windows": "notepad.exe",     "mac": "TextEdit",            "linux": "gedit"},
    "libreoffice":   {"windows": "soffice",         "mac": "LibreOffice",         "linux": "libreoffice"},
    "gimp":          {"windows": "gimp",            "mac": "GIMP",                "linux": "gimp"},
    "settings":      {"windows": "ms-settings:",    "mac": "System Preferences",  "linux": "gnome-control-center"},
}

_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole",
    "xfce4-terminal", "xterm", "lxterminal",
]


def _resolve_target(app_name: str) -> str:
    key = app_name.lower().strip()
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(get_os(), app_name)
    for alias, os_map in _APP_ALIASES.items():
        if alias in key or key in alias:
            return os_map.get(get_os(), app_name)
    return app_name


def _launch_windows(target: str) -> bool:
    try:
        os.startfile(target)  # native, async, os-module only
        return True
    except OSError as e:
        log("OpenApp", f"\u26a0\ufe0f os.startfile failed for '{target}': {e}")
        return False


def _launch_mac(target: str) -> bool:
    # 'open' returns as soon as the app is launched (it doesn't block until
    # the app quits), so no trailing '&' is needed — and omitting it means
    # os.system's exit code actually reflects whether 'open' succeeded.
    safe = target.replace('"', '\\"')
    exit_code = os.system(f'open -a "{safe}" >/dev/null 2>&1')
    if exit_code == 0:
        return True
    # Fall back to treating it as a raw binary on PATH
    binary = which(target)
    if binary:
        os.system(f'"{binary}" >/dev/null 2>&1 &')
        return True
    return False


def _launch_linux(target: str) -> bool:
    if target in ("x-terminal-emulator", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if which(term):
                os.system(f"{term} >/dev/null 2>&1 &")
                return True
        return False

    binary = (
        which(target)
        or which(target.lower())
        or which(target.lower().replace(" ", "-"))
    )
    if binary:
        os.system(f'"{binary}" >/dev/null 2>&1 &')
        return True

    # Last resort: let the desktop's file-association handler try. xdg-open
    # forks and returns on its own, so — like macOS 'open' above — no
    # trailing '&' is needed and the exit code is meaningful.
    if which("xdg-open") is None:
        return False
    exit_code = os.system(f'xdg-open "{target}" >/dev/null 2>&1')
    return exit_code == 0


_LAUNCHERS = {"windows": _launch_windows, "mac": _launch_mac, "linux": _launch_linux}


def open_app(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    app_name = params.get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    launcher = _LAUNCHERS.get(get_os())
    if launcher is None:
        return f"Unsupported operating system: {get_os()}"

    target = _resolve_target(app_name)
    log("OpenApp", f"Launching '{app_name}' \u2192 '{target}' ({get_os()})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        if launcher(target):
            return f"Opened {app_name}."
        if target != app_name and launcher(app_name):
            return f"Opened {app_name}."
        return f"Could not open {app_name}. It may not be installed, or isn't on PATH."
    except Exception as e:
        log("OpenApp", f"\u274c {e}")
        return f"Failed to open {app_name}: {e}"