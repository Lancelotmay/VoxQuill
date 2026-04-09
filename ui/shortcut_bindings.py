import json
import os

from PyQt6.QtGui import QKeySequence, QShortcut

from core.logging_utils import log
from core.path_utils import get_config_path


DEFAULT_SHORTCUTS_PATH = get_config_path("shortcuts.json")


class ShortcutBindingManager:
    def __init__(self, config_path=DEFAULT_SHORTCUTS_PATH):
        self.config_path = config_path
        self._action_definitions = {}
        self._bindings = {}
        self._shortcuts = []

    def set_actions(self, action_definitions):
        self._action_definitions = dict(action_definitions)
        self._bindings = self.load_bindings()

    def defaults(self):
        defaults = {}
        for action_id, definition in self._action_definitions.items():
            defaults[action_id] = list(definition.default_shortcuts)
        return defaults

    def load_bindings(self):
        defaults = self.defaults()
        if not os.path.exists(self.config_path):
            return defaults

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            log(f"Shortcut: failed to load bindings: {e}")
            return defaults

        if not isinstance(raw, dict):
            return defaults

        merged = {}
        for action_id, default_sequences in defaults.items():
            value = raw.get(action_id, default_sequences)
            sequences = self._coerce_sequences(value)
            existing = {**defaults, **merged}
            if not self.validate_binding(action_id, sequences, existing):
                log(f"Shortcut: invalid binding for {action_id}, using defaults")
                sequences = list(default_sequences)
            merged[action_id] = sequences
        return merged

    def save_bindings(self, bindings):
        defaults = self.defaults()
        merged = {}
        for action_id in defaults:
            sequences = self._coerce_sequences(bindings.get(action_id, defaults[action_id]))
            existing = {**defaults, **merged}
            if not self.validate_binding(action_id, sequences, existing):
                raise ValueError(f"Invalid shortcut binding for {action_id}")
            merged[action_id] = sequences

        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        self._bindings = merged

    def bindings(self):
        if not self._bindings:
            self._bindings = self.load_bindings()
        return dict(self._bindings)

    def reset_to_defaults(self):
        self._bindings = self.defaults()
        self.save_bindings(self._bindings)

    def validate_binding(self, action_id, sequences, existing=None):
        if action_id not in self._action_definitions:
            return False
        if not isinstance(sequences, list):
            return False

        normalized = set()
        for sequence in sequences:
            if not isinstance(sequence, str):
                return False
            portable = QKeySequence(sequence).toString(QKeySequence.SequenceFormat.PortableText)
            if not portable:
                return False
            normalized.add(portable)

        existing = existing or self._bindings or self.defaults()
        for other_action_id, other_sequences in existing.items():
            if other_action_id == action_id:
                continue
            other_normalized = {
                QKeySequence(seq).toString(QKeySequence.SequenceFormat.PortableText)
                for seq in self._coerce_sequences(other_sequences)
            }
            if normalized & other_normalized:
                return False
        return True

    def apply_to_window(self, window, callback):
        for shortcut in self._shortcuts:
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._shortcuts = []

        for action_id, definition in self._action_definitions.items():
            if not definition.user_configurable and not definition.default_shortcuts:
                continue
            for sequence in self._bindings.get(action_id, list(definition.default_shortcuts)):
                shortcut = QShortcut(QKeySequence(sequence), window)
                shortcut.activated.connect(
                    lambda action_id=action_id: callback(action_id, source="shortcut")
                )
                self._shortcuts.append(shortcut)

    def _coerce_sequences(self, value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []
