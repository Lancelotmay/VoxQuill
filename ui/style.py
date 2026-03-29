from pathlib import Path

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QWidget


PRIMARY_BLUE = "#007AFF"
# Backward-compatible export for code paths that still import the old tray/icon accent.
WARM_GOLD = PRIMARY_BLUE
SURFACE_SHADOW = QColor(20, 27, 37, 45)


def load_app_stylesheet() -> str:
    qss_path = Path(__file__).with_name("app.qss")
    return qss_path.read_text(encoding="utf-8")


def apply_surface_shadow(widget: QWidget, blur_radius: int = 30, y_offset: int = 8) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(0, y_offset)
    shadow.setColor(SURFACE_SHADOW)
    widget.setGraphicsEffect(shadow)
