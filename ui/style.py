import json
from pathlib import Path

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget


PRIMARY_BLUE = "#007AFF"
# Backward-compatible export for code paths that still import the old tray/icon accent.
WARM_GOLD = PRIMARY_BLUE
SURFACE_SHADOW = QColor(20, 27, 37, 45)
DEFAULT_THEME = "light"
DEFAULT_INACTIVE_OPACITY = 0.72

THEMES = {
    "light": {
        "TEXT_PRIMARY": "#3C3C43",
        "TEXT_STRONG": "#1C1C1E",
        "SURFACE_BG": "#FFFFFF",
        "SURFACE_BORDER": "rgba(0, 0, 0, 0.08)",
        "TOOLTIP_BG": "#1C1C1E",
        "TOOLTIP_TEXT": "#FFFFFF",
        "SELECTION_BG": "#007AFF",
        "SELECTION_TEXT": "#FFFFFF",
        "INPUT_CONTAINER_BG": "rgba(0, 0, 0, 0.03)",
        "INPUT_CONTAINER_BORDER": "rgba(0, 0, 0, 0.05)",
        "BUTTON_HOVER_BG": "rgba(0, 0, 0, 0.05)",
        "BUTTON_PRESSED_BG": "rgba(0, 0, 0, 0.1)",
        "GHOST_BUTTON_TEXT": "rgba(60, 60, 67, 0.7)",
        "GHOST_BUTTON_HOVER_TEXT": "#000000",
        "MODEL_BUTTON_TEXT": "#007AFF",
        "CLOSE_BUTTON_TEXT": "rgba(60, 60, 67, 0.4)",
        "CLOSE_BUTTON_HOVER_BG": "#FF3B30",
        "CLOSE_BUTTON_HOVER_TEXT": "#FFFFFF",
        "MENU_BG": "#FFFFFF",
        "MENU_BORDER": "rgba(0, 0, 0, 0.1)",
        "MENU_SELECTED_BG": "#007AFF",
        "MENU_SELECTED_TEXT": "#FFFFFF",
        "MODEL_ROW_BG": "#FFFFFF",
        "MODEL_ROW_BORDER": "rgba(0, 0, 0, 0.06)",
        "MODEL_ROW_HOVER_BORDER": "rgba(0, 122, 255, 0.2)",
        "MODEL_ROW_SELECTED_BORDER": "#007AFF",
        "MODEL_ROW_SELECTED_BG": "rgba(0, 122, 255, 0.02)",
        "DIALOG_GHOST_BG": "rgba(0, 0, 0, 0.05)",
        "DIALOG_GHOST_TEXT": "#3C3C43",
        "PROGRESS_BG": "rgba(0, 0, 0, 0.05)",
        "PROGRESS_CHUNK_BG": "#007AFF",
        "LANGUAGE_LABEL_TEXT": "rgba(60, 60, 67, 0.4)",
        "LANGUAGE_TAG_BG": "rgba(0, 0, 0, 0.05)",
        "LANGUAGE_TAG_TEXT": "#3C3C43",
        "LANGUAGE_TAG_BORDER": "rgba(0, 0, 0, 0.05)",
        "LANGUAGE_TAG_HOVER_BG": "rgba(0, 0, 0, 0.08)",
        "LANGUAGE_TAG_CHECKED_BG": "#007AFF",
        "LANGUAGE_TAG_CHECKED_TEXT": "#FFFFFF",
        "LANGUAGE_TAG_CHECKED_BORDER": "#007AFF",
        "LANGUAGE_TAG_CHECKED_HOVER_BG": "#0062CC",
    },
    "dark": {
        "TEXT_PRIMARY": "#E5E7EB",
        "TEXT_STRONG": "#F9FAFB",
        "SURFACE_BG": "#16181D",
        "SURFACE_BORDER": "rgba(255, 255, 255, 0.10)",
        "TOOLTIP_BG": "#F3F4F6",
        "TOOLTIP_TEXT": "#111827",
        "SELECTION_BG": "#4C8DFF",
        "SELECTION_TEXT": "#FFFFFF",
        "INPUT_CONTAINER_BG": "rgba(255, 255, 255, 0.06)",
        "INPUT_CONTAINER_BORDER": "rgba(255, 255, 255, 0.08)",
        "BUTTON_HOVER_BG": "rgba(255, 255, 255, 0.08)",
        "BUTTON_PRESSED_BG": "rgba(255, 255, 255, 0.14)",
        "GHOST_BUTTON_TEXT": "rgba(229, 231, 235, 0.72)",
        "GHOST_BUTTON_HOVER_TEXT": "#FFFFFF",
        "MODEL_BUTTON_TEXT": "#6EA8FF",
        "CLOSE_BUTTON_TEXT": "rgba(229, 231, 235, 0.45)",
        "CLOSE_BUTTON_HOVER_BG": "#FF5F57",
        "CLOSE_BUTTON_HOVER_TEXT": "#FFFFFF",
        "MENU_BG": "#1E222B",
        "MENU_BORDER": "rgba(255, 255, 255, 0.10)",
        "MENU_SELECTED_BG": "#4C8DFF",
        "MENU_SELECTED_TEXT": "#FFFFFF",
        "MODEL_ROW_BG": "#1B1F27",
        "MODEL_ROW_BORDER": "rgba(255, 255, 255, 0.08)",
        "MODEL_ROW_HOVER_BORDER": "rgba(110, 168, 255, 0.45)",
        "MODEL_ROW_SELECTED_BORDER": "#6EA8FF",
        "MODEL_ROW_SELECTED_BG": "rgba(110, 168, 255, 0.10)",
        "DIALOG_GHOST_BG": "rgba(255, 255, 255, 0.08)",
        "DIALOG_GHOST_TEXT": "#E5E7EB",
        "PROGRESS_BG": "rgba(255, 255, 255, 0.08)",
        "PROGRESS_CHUNK_BG": "#6EA8FF",
        "LANGUAGE_LABEL_TEXT": "rgba(229, 231, 235, 0.45)",
        "LANGUAGE_TAG_BG": "rgba(255, 255, 255, 0.08)",
        "LANGUAGE_TAG_TEXT": "#E5E7EB",
        "LANGUAGE_TAG_BORDER": "rgba(255, 255, 255, 0.10)",
        "LANGUAGE_TAG_HOVER_BG": "rgba(255, 255, 255, 0.14)",
        "LANGUAGE_TAG_CHECKED_BG": "#6EA8FF",
        "LANGUAGE_TAG_CHECKED_TEXT": "#0F172A",
        "LANGUAGE_TAG_CHECKED_BORDER": "#6EA8FF",
        "LANGUAGE_TAG_CHECKED_HOVER_BG": "#8DB9FF",
    },
}


def clamp_inactive_opacity(value) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        return DEFAULT_INACTIVE_OPACITY
    return max(0.1, min(opacity, 1.0))


def load_ui_preferences(config_path: str | None = None) -> dict:
    resolved_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "config" / "ui.json"
    prefs = {
        "theme": DEFAULT_THEME,
        "inactive_opacity": DEFAULT_INACTIVE_OPACITY,
    }
    if not resolved_path.exists():
        return prefs

    try:
        loaded = json.loads(resolved_path.read_text(encoding="utf-8"))
    except Exception:
        return prefs

    theme = loaded.get("theme", DEFAULT_THEME)
    prefs["theme"] = theme if theme in THEMES else DEFAULT_THEME
    prefs["inactive_opacity"] = clamp_inactive_opacity(loaded.get("inactive_opacity", DEFAULT_INACTIVE_OPACITY))
    return prefs


def save_ui_preferences(preferences: dict, config_path: str | None = None) -> dict:
    resolved_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "config" / "ui.json"
    sanitized = {
        "theme": preferences.get("theme", DEFAULT_THEME),
        "inactive_opacity": clamp_inactive_opacity(preferences.get("inactive_opacity", DEFAULT_INACTIVE_OPACITY)),
    }
    if sanitized["theme"] not in THEMES:
        sanitized["theme"] = DEFAULT_THEME
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    return sanitized


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return hex_color
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _palette_with_inactive_state(theme: str, inactive_opacity: float) -> dict:
    palette = THEMES.get(theme, THEMES[DEFAULT_THEME]).copy()
    alpha = clamp_inactive_opacity(inactive_opacity)
    palette["INACTIVE_SURFACE_BG"] = _hex_to_rgba(palette["SURFACE_BG"], alpha)
    palette["INACTIVE_SURFACE_BORDER"] = (
        "rgba(0, 0, 0, 0.04)" if theme == "light" else "rgba(255, 255, 255, 0.06)"
    )
    palette["INACTIVE_INPUT_CONTAINER_BG"] = (
        "rgba(0, 0, 0, 0.015)" if theme == "light" else "rgba(255, 255, 255, 0.035)"
    )
    palette["INACTIVE_INPUT_CONTAINER_BORDER"] = (
        "rgba(0, 0, 0, 0.03)" if theme == "light" else "rgba(255, 255, 255, 0.05)"
    )
    return palette


def load_app_stylesheet(theme: str = DEFAULT_THEME, inactive_opacity: float = DEFAULT_INACTIVE_OPACITY) -> str:
    qss_path = Path(__file__).with_name("app.qss")
    stylesheet = qss_path.read_text(encoding="utf-8")
    palette = _palette_with_inactive_state(theme, inactive_opacity)
    for key, value in palette.items():
        stylesheet = stylesheet.replace(f"{{{{{key}}}}}", value)
    return stylesheet


def apply_surface_shadow(widget: QWidget, blur_radius: int = 30, y_offset: int = 8) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(0, y_offset)
    shadow.setColor(SURFACE_SHADOW)
    widget.setGraphicsEffect(shadow)
