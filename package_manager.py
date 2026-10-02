"""
package_manager.py — JOI 2.0 system package update/upgrade.

Built primarily on os/sys:
  - os.popen()   -> capture command output (part of the os module itself,
                    so no subprocess dependency for read-only checks)
  - os.system()  -> run update/upgrade commands, using the shell's own exit
                    status to report success/failure

Detects the system's package manager via joi_base.which() and maps a small
set of actions (check / update / upgrade / full) onto the right commands:

    Linux : apt (Pardus/Debian/Ubuntu) > dnf > yum > pacman > zypper
    macOS : brew
    Windows: winget

Root/admin note: update and upgrade need elevated privileges. Rather than
risk os.system silently hanging on a sudo password prompt (or failing with
a confusing error) when JOI is running headless/non-interactively, this
module first checks whether passwordless sudo is available. If it isn't,
it does NOT attempt the privileged command — it hands back the exact
command for the user to run themselves. This keeps the module honest about
what it actually did, with zero network access required for any of it
(besides the package manager's own downloads during update/upgrade).

Call signature matches JOI's existing tool modules:
    package_manager(parameters, response=None, player=None, session_memory=None)
"""
import os

from joi_base import get_os, is_linux, is_mac, is_windows, which, log


# manager_name -> {"check": .., "update": .., "upgrade": .., "needs_root": bool}
_LINUX_MANAGERS = [
    ("apt", {
        "check":   "apt list --upgradable 2>/dev/null | tail -n +2",
        "update":  "sudo apt-get update -y",
        "upgrade": "sudo apt-get upgrade -y",
        "needs_root": True,
    }),
    ("dnf", {
        "check":   "dnf check-update --quiet",
        "update":  "sudo dnf makecache",
        "upgrade": "sudo dnf upgrade -y",
        "needs_root": True,
    }),
    ("yum", {
        "check":   "yum check-update --quiet",
        "update":  "sudo yum makecache",
        "upgrade": "sudo yum update -y",
        "needs_root": True,
    }),
    ("pacman", {
        "check":   "pacman -Qu",
        "update":  "sudo pacman -Sy",
        "upgrade": "sudo pacman -Syu --noconfirm",
        "needs_root": True,
    }),
    ("zypper", {
        "check":   "zypper lu",
        "update":  "sudo zypper refresh",
        "upgrade": "sudo zypper update -y",
        "needs_root": True,
    }),
]

_MAC_MANAGER = ("brew", {
    "check":   "brew outdated",
    "update":  "brew update",
    "upgrade": "brew upgrade",
    "needs_root": False,
})

_WIN_MANAGER = ("winget", {
    "check":   "winget upgrade --accept-source-agreements",
    "update":  "winget source update",
    "upgrade": "winget upgrade --all --silent --accept-source-agreements --accept-package-agreements",
    "needs_root": False,
})


def _detect_manager():
    """Returns (name, commands_dict) for the first available manager, or None."""
    if is_linux():
        for name, cmds in _LINUX_MANAGERS:
            if which(name):
                return name, cmds
        return None
    if is_mac():
        name, cmds = _MAC_MANAGER
        return (name, cmds) if which(name) else None
    if is_windows():
        name, cmds = _WIN_MANAGER
        return (name, cmds) if which(name) else None
    return None


def _has_passwordless_sudo() -> bool:
    """os.system-only check — avoids ever blocking on a hidden password prompt."""
    return os.system("sudo -n true >/dev/null 2>&1") == 0


def _run_capture(cmd: str) -> str:
    """Capture command output via os.popen — stdlib os module, no subprocess."""
    try:
        with os.popen(cmd) as stream:
            return stream.read().strip()
    except OSError as e:
        return f"(failed to run command: {e})"


def _run(cmd: str) -> bool:
    return os.system(cmd) == 0


def _check(name: str, cmds: dict) -> str:
    output = _run_capture(cmds["check"])
    if not output:
        return f"[{name}] Everything is up to date."
    lines = output.splitlines()
    header = f"[{name}] {len(lines)} package(s) can be upgraded:"
    return header + "\n" + "\n".join(lines[:30]) + ("\n..." if len(lines) > 30 else "")


def _privileged_step(name: str, cmds: dict, key: str) -> str:
    cmd = cmds[key]
    if cmds["needs_root"] and not _has_passwordless_sudo():
        return (
            f"[{name}] This needs a sudo password, which I can't enter for you. "
            f"Run this yourself:\n  {cmd}"
        )
    ok = _run(cmd)
    action_word = "updated package index" if key == "update" else "upgraded packages"
    return f"[{name}] Successfully {action_word}." if ok else f"[{name}] Command failed: {cmd}"


# ── Public tool entry point (matches JOI's existing tool signature) ────────
def package_manager(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
      action : check | update | upgrade | full   (default: check)
        check   -> list what's upgradable, no changes made
        update  -> refresh the package index only
        upgrade -> upgrade already-installed packages
        full    -> update then upgrade
    """
    params = parameters or {}
    action = params.get("action", "check").lower().strip()

    detected = _detect_manager()
    if detected is None:
        return f"No supported package manager found for {get_os()}."
    name, cmds = detected

    if player:
        player.write_log(f"[PackageManager] {name} {action}")
    log("PackageManager", f"\u25b6 {name} / {action}")

    try:
        if action == "check":
            return _check(name, cmds)
        if action == "update":
            return _privileged_step(name, cmds, "update")
        if action == "upgrade":
            return _privileged_step(name, cmds, "upgrade")
        if action == "full":
            update_result = _privileged_step(name, cmds, "update")
            if "sudo password" in update_result:
                return update_result  # don't chain into upgrade if we can't even update
            upgrade_result = _privileged_step(name, cmds, "upgrade")
            return update_result + "\n" + upgrade_result

        return f"Unknown package_manager action: '{action}'. Available: check, update, upgrade, full."

    except Exception as e:
        log("PackageManager", f"\u274c {action} failed: {e}")
        return f"package_manager '{action}' failed: {e}"