import sys
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.wayland_portal import PortalError, WaylandPortalKeyboard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-window", default="")
    args = parser.parse_args()

    keyboard = WaylandPortalKeyboard(allow_helper_fallback=False)
    if not keyboard.is_available():
        raise PortalError("Portal backend is unavailable in helper environment")
    result = keyboard.paste_ctrl_v(parent_window=args.parent_window)
    if not result.success:
        raise PortalError(result.error_message or "Portal helper paste failed")
    print("portal-helper-ok", flush=True)


if __name__ == "__main__":
    main()
