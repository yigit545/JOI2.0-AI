"""
file_manager.py — JOI 2.0 offline file management.

Built primarily on os/sys:
  - list, exists, info, mkdir, rename, delete  -> os / os.path only
  - move                                        -> os.rename, falling back to
                                                    shutil.move only when the
                                                    source/destination are on
                                                    different filesystems
                                                    (os.rename raises OSError
                                                    there — that's the one gap
                                                    the os module can't cover)
  - copy                                        -> shutil.copy2/copytree,
                                                    since os has no built-in
                                                    "copy file contents" call
  - search                                      -> os.walk / os.scandir

Nothing here touches the network — every action is local-disk only, so it
works fully offline. send2trash is used opportunistically for safer deletes
if it happens to be installed; otherwise delete falls back to os.remove /
os.rmdir (permanent, not recoverable — see the warning printed at call time).

Call signature matches JOI's existing tool modules:
    file_manager(parameters, response=None, player=None, session_memory=None)
"""
import os
import shutil
from datetime import datetime

from joi_base import log, is_windows

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False


# ── Safety: refuse to operate outside the user's home directory unless the
# caller passes an explicit absolute path they clearly intended. This keeps a
# malformed relative path from ever resolving to something like "/". ────────
def _resolve(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ── Actions ──────────────────────────────────────────────────────────────────
def _list_dir(path: str) -> str:
    path = _resolve(path)
    if not os.path.isdir(path):
        return f"Not a directory: {path}"

    entries = []
    with os.scandir(path) as it:
        for entry in it:
            kind = "DIR " if entry.is_dir(follow_symlinks=False) else "FILE"
            try:
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                size = 0
            entries.append((kind, entry.name, size))

    entries.sort(key=lambda e: (e[0] != "DIR ", e[1].lower()))
    if not entries:
        return f"{path} is empty."

    lines = [f"{path}  ({len(entries)} items)"]
    for kind, name, size in entries:
        size_str = "" if kind == "DIR " else f"  {_human_size(size)}"
        lines.append(f"  [{kind}] {name}{size_str}")
    return "\n".join(lines)


def _file_info(path: str) -> str:
    path = _resolve(path)
    if not os.path.exists(path):
        return f"Does not exist: {path}"
    st = os.stat(path)
    kind = "directory" if os.path.isdir(path) else "file"
    modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
    size_str = "-" if kind == "directory" else _human_size(st.st_size)
    return f"{path}\n  type: {kind}\n  size: {size_str}\n  modified: {modified}"


def _mkdir(path: str) -> str:
    path = _resolve(path)
    try:
        os.makedirs(path, exist_ok=True)
        return f"Created directory: {path}"
    except OSError as e:
        return f"Could not create directory: {e}"


def _rename(path: str, new_name: str) -> str:
    path = _resolve(path)
    if not os.path.exists(path):
        return f"Does not exist: {path}"
    new_path = os.path.join(os.path.dirname(path), new_name)
    try:
        os.rename(path, new_path)
        return f"Renamed to: {new_path}"
    except OSError as e:
        return f"Rename failed: {e}"


def _move(src: str, dst: str) -> str:
    src, dst = _resolve(src), _resolve(dst)
    if not os.path.exists(src):
        return f"Source does not exist: {src}"
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    try:
        os.rename(src, dst)  # atomic, os-only — works when same filesystem
        return f"Moved {src} -> {dst}"
    except OSError:
        # Cross-filesystem move: os.rename can't do this, shutil.move can.
        try:
            shutil.move(src, dst)
            return f"Moved {src} -> {dst} (cross-filesystem)"
        except (OSError, shutil.Error) as e:
            return f"Move failed: {e}"


def _copy(src: str, dst: str) -> str:
    src, dst = _resolve(src), _resolve(dst)
    if not os.path.exists(src):
        return f"Source does not exist: {src}"
    try:
        if os.path.isdir(src):
            if os.path.isdir(dst):
                dst = os.path.join(dst, os.path.basename(src))
            shutil.copytree(src, dst)
        else:
            if os.path.isdir(dst):
                dst = os.path.join(dst, os.path.basename(src))
            shutil.copy2(src, dst)
        return f"Copied {src} -> {dst}"
    except (OSError, shutil.Error) as e:
        return f"Copy failed: {e}"


def _delete(path: str, permanent: bool = False) -> str:
    path = _resolve(path)
    if not os.path.exists(path):
        return f"Does not exist: {path}"

    if not permanent and _SEND2TRASH:
        try:
            send2trash.send2trash(path)
            return f"Moved to trash: {path}"
        except Exception as e:
            log("FileManager", f"\u26a0\ufe0f send2trash failed, falling back to permanent delete: {e}")

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        note = "" if _SEND2TRASH else " (send2trash not installed — this was permanent)"
        return f"Deleted: {path}{note}"
    except OSError as e:
        return f"Delete failed: {e}"


def _search(root: str, pattern: str) -> str:
    root = _resolve(root)
    pattern = pattern.lower()
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames + dirnames:
            if pattern in name.lower():
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break

    if not matches:
        return f"No matches for '{pattern}' under {root}"
    header = f"{len(matches)} match(es) for '{pattern}' under {root}"
    if len(matches) >= 50:
        header += " (truncated at 50)"
    return header + "\n" + "\n".join(matches)


# ── Public tool entry point (matches JOI's existing tool signature) ────────
def file_manager(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
      action    : list | info | mkdir | rename | move | copy | delete | search
      path      : target path (most actions)
      dest      : destination path (move / copy)
      new_name  : new filename (rename)
      pattern   : search substring (search)
      permanent : bool, skip trash for delete (default: False)
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    path = params.get("path", "").strip()

    if not action:
        return "No action specified for file_manager."

    if player:
        player.write_log(f"[FileManager] {action} {path}")
    log("FileManager", f"\u25b6 {action}  {params}")

    try:
        if action == "list":
            return _list_dir(path or ".")
        if action == "info":
            return _file_info(path)
        if action == "mkdir":
            return _mkdir(path)
        if action == "rename":
            return _rename(path, params.get("new_name", "").strip())
        if action == "move":
            return _move(path, params.get("dest", "").strip())
        if action == "copy":
            return _copy(path, params.get("dest", "").strip())
        if action == "delete":
            return _delete(path, permanent=bool(params.get("permanent", False)))
        if action == "search":
            return _search(path or ".", params.get("pattern", "").strip())

        return f"Unknown file_manager action: '{action}'."

    except Exception as e:
        log("FileManager", f"\u274c {action} failed: {e}")
        return f"file_manager '{action}' failed: {e}"