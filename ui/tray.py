from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap
from PyQt6.QtCore import Qt
from core.path_utils import get_resource_path


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, parent_window, start_callback, stop_callback, quit_callback):
        # Use initial idle icon
        self.idle_icon = QIcon(get_resource_path("resource/main_small_color_blue_256.png"))
        self.recording_icon = QIcon(get_resource_path("resource/main_small_color_256.png"))
        
        super().__init__(self.idle_icon, parent_window)
        self.parent_window = parent_window
        self.setToolTip("VoxQuill")
        
        # Create Menu
        self.menu = QMenu()
        
        self.show_action = QAction("Show Window")
        self.show_action.triggered.connect(self.parent_window.show)
        self.menu.addAction(self.show_action)
        
        self.hide_action = QAction("Hide Window")
        self.hide_action.triggered.connect(self.parent_window.hide)
        self.menu.addAction(self.hide_action)
        
        self.menu.addSeparator()
        
        self.start_action = QAction("Start Recording")
        self.start_action.triggered.connect(start_callback)
        self.menu.addAction(self.start_action)
        
        self.stop_action = QAction("Stop Recording")
        self.stop_action.triggered.connect(stop_callback)
        self.menu.addAction(self.stop_action)
        
        self.menu.addSeparator()
        
        self.quit_action = QAction("Quit")
        self.quit_action.triggered.connect(quit_callback)
        self.menu.addAction(self.quit_action)
        
        self.setContextMenu(self.menu)
        
        # Double click to toggle visibility
        self.activated.connect(self._on_activated)
        
    def set_recording_state(self, is_recording):
        self.setIcon(self.recording_icon if is_recording else self.idle_icon)
        self.start_action.setEnabled(not is_recording)
        self.stop_action.setEnabled(is_recording)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.parent_window.isVisible():
                self.parent_window.hide()
            else:
                self.parent_window.show()
                self.parent_window.raise_()
