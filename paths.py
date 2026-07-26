import sys
from pathlib import Path


def app_dir():
    """Directory to store user data in - beside the exe when frozen, beside the script otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resource_dir():
    """Directory holding bundled read-only assets (e.g. icon.ico) - PyInstaller's
    onefile extraction dir when frozen, beside the script otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent
