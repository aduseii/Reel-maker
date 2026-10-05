"""Starts Reel Maker. If anything fails while starting, it shows a message and
saves the details to %LOCALAPPDATA%\ReelMaker\error.log instead of failing silently."""
import os
import sys
import traceback

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
try:
    import reel_maker
    reel_maker.main()
except SystemExit:
    raise
except BaseException:
    text = traceback.format_exc()
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ReelMaker")
    log = os.path.join(log_dir, "error.log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, "Reel Maker couldn't start.\n\n" + text[-900:] + "\n\nDetails saved to:\n" + log,
            "Reel Maker", 0x10)
    except Exception:
        pass
