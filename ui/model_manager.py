from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QLineEdit,
    QFileDialog,
    QCheckBox,
)
from PyQt6.QtGui import QCursor

from core.asr_config import (
    delete_model,
    download_model,
    get_model_catalog,
    set_active_model,
    load_asr_config,
    get_global_languages,
    set_global_languages,
    get_history_dir,
    set_history_dir,
    get_history_enabled,
    set_history_enabled,
)
from ui.style import apply_surface_shadow


class DownloadWorker(QObject):
    progress = pyqtSignal(str, str, object)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_id):
        super().__init__()
        self.model_id = model_id

    def run(self):
        try:
            download_model(self.model_id, progress_cb=self._emit_progress)
            self.finished.emit(self.model_id)
        except Exception as e:
            self.failed.emit(str(e))

    def _emit_progress(self, stage, message, value):
        self.progress.emit(stage, message, value)


class ModelRow(QWidget):
    activate_requested = pyqtSignal(str, str)
    download_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str, str)
    language_requested = pyqtSignal(str, str) # Added signal

    def __init__(self, model, downloading=False, parent=None):
        super().__init__(parent)
        self.model = model
        self._downloading = downloading
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("ModelRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.radio = QRadioButton()
        self.radio.setChecked(self.model["active"])
        self.radio.setEnabled(self.model["installed"] and self.model["loadable"] and not self._downloading)
        self.radio.toggled.connect(self._on_radio_toggled)
        layout.addWidget(self.radio, 0, Qt.AlignmentFlag.AlignVCenter)
        
        # Add visual property for QSS
        self.setProperty("selected", self.model["active"])

        info_widget = QWidget()
        info_widget.setObjectName("ModelInfo")
        info_col = QVBoxLayout(info_widget)
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        title = QLabel(self.model["display_name"])
        title.setObjectName("ModelName")
        info_col.addWidget(title)

        desc = self.model.get("description") or "No description"
        if self.model["installed"] and not self.model["loadable"] and self.model["load_error"]:
            desc = f"{desc}  Load error: {self.model['load_error']}"
        desc_label = QLabel(desc)
        desc_label.setObjectName("ModelDescription")
        desc_label.setWordWrap(True)
        info_col.addWidget(desc_label)

        meta_row = QWidget()
        meta_row.setObjectName("MetaRow")
        meta_layout = QHBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(6)
        meta_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for badge_text in self._meta_items():
            badge = QLabel(badge_text)
            badge.setObjectName("ModelBadge")
            meta_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        meta_layout.addStretch()
        info_col.addWidget(meta_row)

        layout.addWidget(info_widget, 1, Qt.AlignmentFlag.AlignVCenter)

        actions_widget = QWidget()
        actions_widget.setObjectName("ModelActions")
        action_row = QHBoxLayout(actions_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.download_button = QPushButton("Update" if self.model["installed"] else "Download")
        self.download_button.setObjectName("PrimaryAction")
        self.download_button.setEnabled(not self._downloading)
        self.download_button.clicked.connect(
            lambda: self.download_requested.emit(self.model["id"], self.model["display_name"])
        )
        action_row.addWidget(self.download_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.delete_button = QPushButton("Remove")
        self.delete_button.setObjectName("DangerAction")
        self.delete_button.setEnabled(self.model["installed"] and not self._downloading)
        self.delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self.model["id"], self.model["display_name"])
        )
        action_row.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(actions_widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def _meta_items(self):
        status = "Not installed"
        if self.model["installed"] and self.model["loadable"]:
            status = "Installed"
        elif self.model["installed"] and not self.model["loadable"]:
            status = "Installed, invalid"
        if self.model["active"]:
            status = "Default"
        return [self.model["pipeline"], status]

    def _on_radio_toggled(self, checked):
        if checked:
            self.setProperty("selected", True)
            self.style().unpolish(self)
            self.style().polish(self)
            self.activate_requested.emit(self.model["id"], self.model["display_name"])
        else:
            self.setProperty("selected", False)
            self.style().unpolish(self)
            self.style().polish(self)


class LanguageTag(QPushButton):
    def __init__(self, text, code, checked=False, parent=None):
        super().__init__(text, parent)
        self.code = code
        self.setCheckable(True)
        self.setChecked(checked)
        self.setObjectName("LanguageTag")
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class LanguageSelector(QWidget):
    languages_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tags = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        label = QLabel("Languages:")
        label.setObjectName("LanguageSelectorLabel")
        layout.addWidget(label)

        langs = [
            ("ZH", "zh"),
            ("EN", "en"),
            ("JA", "ja"),
            ("KO", "ko"),
            ("YUE", "yue"),
        ]
        
        current_langs = get_global_languages()
        
        for text, code in langs:
            tag = LanguageTag(text, code, checked=(code in current_langs))
            tag.toggled.connect(self._on_tag_toggled)
            layout.addWidget(tag)
            self.tags.append(tag)

    def _on_tag_toggled(self):
        selected = [tag.code for tag in self.tags if tag.isChecked()]
        # Prevent selecting none (at least auto)
        if not selected:
             # If nothing selected, maybe treat as all? Or force one?
             # User said multi-select. If they deselect all, we might want to reset to all or show warn.
             pass
        self.languages_changed.emit(selected)


class ModelManagerDialog(QDialog):
    models_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._download_thread = None
        self._download_worker = None
        self._current_download_model_id = None
        self._selected_model_id = load_asr_config()["id"]

        self.setWindowTitle("Model Manager")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(800, 620)
        self._setup_ui()
        self.refresh_models()

    def center_on_current_screen(self):
        cursor_screen = QApplication.screenAt(QCursor.pos()) or self.screen()
        if cursor_screen is None:
            return
        geometry = cursor_screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + (geometry.height() - self.height()) // 2
        self.move(x, y)

    def _setup_ui(self):
        self.setObjectName("ModelManagerDialog")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        self.surface = QWidget()
        self.surface.setObjectName("Surface")
        apply_surface_shadow(self.surface, blur_radius=28, y_offset=8)
        outer.addWidget(self.surface)

        layout = QVBoxLayout(self.surface)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.header_bar = QWidget()
        self.header_bar.setObjectName("HeaderBar")
        header = QHBoxLayout(self.header_bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.title_label = QLabel("Models")
        self.title_label.setObjectName("DialogTitle")
        header.addWidget(self.title_label)

        header.addStretch()

        close_button = QPushButton("×")
        close_button.setObjectName("CloseButton")
        close_button.clicked.connect(self.accept)
        header.addWidget(close_button)
        layout.addWidget(self.header_bar)

        self.status_label = QLabel("Set the default model here. Download links stay in the config file.")
        self.status_label.setObjectName("DialogHint")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Global Language Selector
        self.lang_selector = LanguageSelector()
        self.lang_selector.languages_changed.connect(self._on_global_langs_changed)
        layout.addWidget(self.lang_selector)
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(0, 4, 0, 4)
        history_layout.setSpacing(4)
        
        # 1. Enable Checkbox
        self.history_enabled_check = QCheckBox("Enable History Logging")
        self.history_enabled_check.setChecked(get_history_enabled())
        self.history_enabled_check.toggled.connect(set_history_enabled)
        history_layout.addWidget(self.history_enabled_check)
        
        # 2. Path Horizontal Row
        history_path_row = QWidget()
        history_path_layout = QHBoxLayout(history_path_row)
        history_path_layout.setContentsMargins(0, 0, 0, 0)
        history_path_layout.setSpacing(8)
        
        target_label = QLabel("Save to:")
        target_label.setObjectName("LanguageSelectorLabel")
        history_path_layout.addWidget(target_label)
        
        self.history_path_edit = QLineEdit()
        self.history_path_edit.setReadOnly(True)
        self.history_path_edit.setText(get_history_dir())
        self.history_path_edit.setObjectName("HistoryPathEdit")
        history_path_layout.addWidget(self.history_path_edit, 1)
        
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("DialogGhost")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._on_browse_history_dir)
        history_path_layout.addWidget(browse_btn)

        history_layout.addWidget(history_path_row)
        
        layout.addWidget(history_widget)
        layout.addSpacing(4)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area, 1)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("RowsContainer")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(12)
        self.scroll_area.setWidget(self.rows_container)
        
        # 4. Footer Row
        self.footer_bar = QWidget()
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(0, 10, 0, 0)
        footer_layout.setSpacing(10)
        
        footer_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("DialogGhost")
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save && Apply")
        self.save_button.setObjectName("DialogPrimary")
        self.save_button.clicked.connect(self._save_selection)
        footer_layout.addWidget(self.save_button)
        
        layout.addWidget(self.footer_bar)

        self.header_bar.installEventFilter(self)
        self.title_label.installEventFilter(self)

    def refresh_models(self):
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.radio_group = QButtonGroup(self)
        self.radio_group.setExclusive(True)

        for model in get_model_catalog():
            # Virtual check for previewing selection
            model_is_selected = (model["id"] == self._selected_model_id)
            # Create a copy to not modify original catalog objects
            preview_model = model.copy()
            preview_model["active"] = model_is_selected
            
            row = ModelRow(preview_model, downloading=self._download_thread is not None)
            row.activate_requested.connect(self._on_row_selected)
            row.download_requested.connect(self._start_download)
            row.delete_requested.connect(self._delete_model)
            self.radio_group.addButton(row.radio)
            self.rows_layout.addWidget(row)

        self.rows_layout.addStretch()

    def eventFilter(self, obj, event):
        if obj in (self.header_bar, self.title_label) and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
                self.windowHandle().startSystemMove()
                return True
        return super().eventFilter(obj, event)

    def _on_row_selected(self, model_id, display_name):
        self._selected_model_id = model_id
        # We don't refresh all models here to avoid heavy UI rebuild, 
        # the row radio button itself handles the checked state.
        self.status_label.setText(f"Selection: {display_name} (unsaved)")

    def _on_global_langs_changed(self, langs):
        set_global_languages(langs)
        self.status_label.setText(f"Languages: {', '.join(langs)}")

    def _on_browse_history_dir(self):
        current_dir = self.history_path_edit.text()
        new_dir = QFileDialog.getExistingDirectory(self, "Select History Directory", current_dir)
        if new_dir:
            self.history_path_edit.setText(new_dir)
            set_history_dir(new_dir)
            self.status_label.setText(f"History switched to: {new_dir}")

    def _save_selection(self):
        try:
            set_active_model(self._selected_model_id)
            self.models_changed.emit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))

    def _start_download(self, model_id, display_name):
        if self._download_thread is not None:
            return

        self._current_download_model_id = model_id
        self.status_label.setText(f"Preparing download for {display_name}...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self._download_thread = QThread(self)
        self._download_worker = DownloadWorker(model_id)
        self._download_worker.moveToThread(self._download_thread)

        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._cleanup_download)

        self.refresh_models()
        self._download_thread.start()

    def _on_download_progress(self, stage, message, value):
        self.status_label.setText(message)
        if value is None:
            self.progress_bar.setRange(0, 0)
        else:
            if self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))

    def _on_download_finished(self, model_id):
        self.status_label.setText(f"Model '{model_id}' is ready.")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.refresh_models()
        self.models_changed.emit()

    def _on_download_failed(self, error_text):
        self.status_label.setText("Model download failed.")
        self.progress_bar.hide()
        QMessageBox.critical(self, "Download Failed", error_text)
        self.refresh_models()

    def _cleanup_download(self):
        if self._download_worker is not None:
            self._download_worker.deleteLater()
        if self._download_thread is not None:
            self._download_thread.deleteLater()
        self._download_worker = None
        self._download_thread = None
        self._current_download_model_id = None
        self.refresh_models()

    def _delete_model(self, model_id, display_name):
        answer = QMessageBox.question(
            self,
            "Remove Model",
            f"Remove downloaded files for '{display_name}'?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_model(model_id)
        except Exception as e:
            QMessageBox.critical(self, "Remove Failed", str(e))
            return

        self.status_label.setText(f"Removed files for {display_name}.")
        self.progress_bar.hide()
        self.refresh_models()
        self.models_changed.emit()
