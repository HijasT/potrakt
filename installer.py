import sys
from pathlib import Path

import win32com.client

from paths import app_dir


def _target_and_args():
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    script = str(app_dir() / "app.py")
    return pythonw, f'"{script}"'


def _write_shortcut(path, target, args, workdir):
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(path))
    shortcut.TargetPath = target
    shortcut.Arguments = args
    shortcut.WorkingDirectory = workdir
    shortcut.IconLocation = target
    shortcut.Save()


def create_shortcuts():
    """Create a Desktop shortcut and a Start Menu entry for potrakt."""
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = Path(shell.SpecialFolders("Desktop"))
    start_menu = Path(shell.SpecialFolders("Programs"))

    target, args = _target_and_args()
    workdir = str(app_dir())

    _write_shortcut(desktop / "potrakt.lnk", target, args, workdir)
    _write_shortcut(start_menu / "potrakt.lnk", target, args, workdir)
