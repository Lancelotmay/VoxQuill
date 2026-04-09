from dataclasses import dataclass, field

from core.logging_utils import log


@dataclass
class ActionDefinition:
    action_id: str
    display_name: str
    handler: callable
    default_shortcuts: tuple[str, ...] = field(default_factory=tuple)
    user_configurable: bool = True


class ActionRegistry:
    def __init__(self):
        self._definitions = {}

    def register(self, definition: ActionDefinition):
        self._definitions[definition.action_id] = definition

    def trigger(self, action_id, source="unknown"):
        definition = self._definitions[action_id]
        log(f"Action: {action_id} triggered via {source}")
        return definition.handler()

    def definition(self, action_id):
        return self._definitions[action_id]

    def definitions(self):
        return dict(self._definitions)
