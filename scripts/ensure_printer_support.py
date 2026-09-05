"""Best-effort Windows dependency bootstrap, usable by the old update path."""
import subprocess
import sys


def available() -> bool:
    try:
        import win32print  # noqa: F401
        import win32ui  # noqa: F401
        return True
    except ImportError:
        return False


def ensure() -> dict:
    if sys.platform != "win32":
        return {"ok": False, "error": "ბეჭდვა საჭიროებს Windows-ს."}
    if available():
        return {"ok": True}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "--timeout", "15", "--retries", "1", "pywin32==311"],
            capture_output=True, text=True, timeout=75,
        )
        if result.returncode == 0:
            # A fresh Python process loads pywin32's newly installed .pth file.
            check = subprocess.run([sys.executable, "-c", "import win32print, win32ui"],
                                   capture_output=True, text=True, timeout=10)
            if check.returncode == 0:
                return {"ok": True, "restart_required": True}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"ok": False, "error": "პრინტერის კომპონენტი ვერ დაყენდა. შეამოწმეთ ინტერნეტი და სცადეთ თავიდან."}
