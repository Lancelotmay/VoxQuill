import os
import sys

def get_root_dir():
    """Get the root directory of the project.
    Works for both source and PyInstaller environments.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return sys._MEIPASS
    else:
        # Development mode
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path):
    """Get the absolute path to a resource."""
    return os.path.join(get_root_dir(), relative_path)

def get_config_path(filename):
    """Get the absolute path to a configuration file."""
    # Note: For production, we might want to store user config in ~/.config/VoxQuill
    # but for this assessment we'll keep it in the project root/config
    return os.path.join(get_root_dir(), "config", filename)

def get_models_dir():
    """Get the directory where ASR models are stored."""
    # In production, models are huge, so maybe ~/.local/share/VoxQuill/models
    # For now, we'll keep it in the project root
    return os.path.join(get_root_dir(), "models")


def get_state_dir():
    """Get the directory for user-local runtime state."""
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return os.path.join(xdg_state_home, "VoxQuill")
    return os.path.join(os.path.expanduser("~/.local/state"), "VoxQuill")


def get_state_path(filename):
    """Get the absolute path to a state file."""
    return os.path.join(get_state_dir(), filename)
