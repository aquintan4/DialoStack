"""
SessionManager — thread-safe store for active LLM sessions.

Each Session holds its own lock so concurrent requests on *different* sessions
never block each other. Requests on the *same* stateful session are inherently
sequential at the application level (one dialog turn at a time), but the lock
still protects history from any unexpected concurrent access.

Known limitation: build_messages() and commit_turn() are not atomic with
respect to each other. Two concurrent callers on the same session could
interleave their history entries. This is acceptable because the dialog node
never fires two simultaneous turns on the same session; the note is here so
future maintainers don't remove the per-session lock thinking it is redundant.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    """Isolated conversational state for one provider/model pair."""

    session_id: str
    provider: str
    model: str
    system_prompt: str
    stateful: bool
    created_at: float = field(default_factory=time.monotonic)
    _history: list = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def build_messages(self, user_prompt: str) -> list[dict]:
        """Assemble the message list for the provider, snapshot history under lock."""
        with self._lock:
            history_snapshot = list(self._history)

        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(history_snapshot)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def commit_turn(self, user_prompt: str, assistant_reply: str) -> None:
        """Atomically append one completed user/assistant pair to the history."""
        if not self.stateful:
            return
        with self._lock:
            self._history.append({"role": "user", "content": user_prompt})
            self._history.append({"role": "assistant", "content": assistant_reply})

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    @property
    def history_turns(self) -> int:
        with self._lock:
            return len(self._history) // 2


class SessionManager:
    """Thread-safe registry of active sessions."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(
        self,
        session_id: str,
        provider: str,
        model: str,
        system_prompt: str,
        stateful: bool,
    ) -> tuple[bool, str, Optional[Session]]:
        """
        Create and register a new session.

        Returns (True, session_id, session) on success.
        Returns (False, error_message, None) if the id already exists.
        A blank session_id is replaced with a fresh UUID.
        """
        sid = session_id.strip() or str(uuid.uuid4())

        with self._lock:
            if sid in self._sessions:
                return False, f"Session '{sid}' already exists.", None

            session = Session(
                session_id=sid,
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                stateful=stateful,
            )
            self._sessions[sid] = session

        return True, sid, session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> tuple[bool, int]:
        """
        Delete a session by id.

        A non-empty session_id removes that specific session.
        Passing the sentinel value "*" removes all sessions (bulk-clear).
        An empty or missing id returns (False, 0).
        """
        with self._lock:
            if session_id == "*":
                count = len(self._sessions)
                self._sessions.clear()
                return True, count

            if not session_id:
                return False, 0

            removed = self._sessions.pop(session_id, None)
            return (True, 1) if removed is not None else (False, 0)

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "provider": s.provider,
                    "model": s.model,
                    "stateful": s.stateful,
                    "history_turns": s.history_turns,
                }
                for s in self._sessions.values()
            ]
