"""
Per-task contextual data injected into LLM prompts.

Built once per dialog from the action goal (resources, domain) and updated
live with the user's emotional state. Serialised into a [CONTEXT] block
prepended to prompts that opt in to context injection.
"""

import threading
import time
from dataclasses import dataclass, field

_EMOTION_TTL_SECS = 30.0
_EMOTION_MIN_CONFIDENCE = 0.5


@dataclass
class Resource:
    """Static reference data (menus, catalogues, schedules...) attached to a dialog."""

    name: str
    description: str
    content: str


@dataclass
class UserState:
    """Snapshot of the user's affective state at a point in time."""

    emotion: str = "neutral"  # neutral | frustrated | angry | happy | sad
    confidence: float = 0.0
    source: str = "unknown"  # vision | audio | inferred
    timestamp: float = field(default_factory=time.monotonic)

    def is_notable(self, ttl: float = _EMOTION_TTL_SECS) -> bool:
        """True when non-neutral, sufficiently confident, and recent."""
        if self.emotion == "neutral" or self.confidence < _EMOTION_MIN_CONFIDENCE:
            return False
        return (time.monotonic() - self.timestamp) <= ttl


class DialogContext:
    """
    Per-dialog contextual data injected into LLM prompts.

    Resources and domain are static (set once). UserState is updated live
    from the /user_emotion topic and surfaced only when notable.
    """

    def __init__(self, resources: list[Resource] | None = None, domain: str = ""):
        self.resources = list(resources) if resources else []
        self.domain = domain
        self._user_state = UserState()
        self._lock = threading.Lock()

    def update_user_state(self, state: UserState) -> None:
        with self._lock:
            self._user_state = state

    def current_user_state(self) -> UserState:
        with self._lock:
            return self._user_state

    def to_prompt_block(self) -> str:
        """Build the [CONTEXT] block. Returns empty string if nothing to surface."""
        parts: list[str] = []

        if self.domain:
            parts.append(f"Domain context: {self.domain}")

        for r in self.resources:
            header = f"[{r.name}]"
            if r.description:
                header += f" {r.description}"
            parts.append(f"{header}:\n{r.content}")

        state = self.current_user_state()
        if state.is_notable():
            parts.append(
                f"User emotional state: {state.emotion} "
                f"(confidence {state.confidence:.0%}, source: {state.source})"
            )

        if not parts:
            return ""
        return "[CONTEXT]\n" + "\n\n".join(parts) + "\n[/CONTEXT]\n"
