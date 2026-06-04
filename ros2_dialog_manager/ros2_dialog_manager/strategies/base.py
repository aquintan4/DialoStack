"""
Base classes, shared types and strategy registry.

To add a new strategy:
  1. Create a new file in this directory.
  2. Subclass BaseDialogStrategy and implement the abstract methods.
  3. Decorate the class with @register_strategy("mode_name").
  4. Import it in strategies/__init__.py so it registers at import time.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Type

from ..dialog_context import DialogContext
from ..dialog_frame import DialogFrame

if TYPE_CHECKING:
    from ..llm_client import LLMDialogClient


# ==== CONFIG AND OPERATION TYPES ====


@dataclass
class FSMConfig:
    max_turns: int = 0
    max_timeouts: int = 2
    max_unclear: int = 3
    max_attempts: int = 3
    ack_phrases: tuple[str, ...] = ()  # Configured in app_params.yaml; empty = no ack


class OpKind(Enum):
    SET = "set"
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


@dataclass
class Operation:
    slot: str
    kind: OpKind
    value: object  # str for SET, list[str] for ADD/REMOVE/REPLACE


# ==== STRATEGY REGISTRY ====

_STRATEGY_REGISTRY: dict[str, Type["BaseDialogStrategy"]] = {}


def register_strategy(mode: str) -> Callable[[Type], Type]:
    """Class decorator that registers a strategy under a mode name.
    Raises at import time on duplicate registrations."""

    def decorator(cls: Type) -> Type:
        if mode in _STRATEGY_REGISTRY:
            raise ValueError(
                f"Strategy mode '{mode}' already registered to "
                f"{_STRATEGY_REGISTRY[mode].__name__}"
            )
        _STRATEGY_REGISTRY[mode] = cls
        return cls

    return decorator


def available_modes() -> list[str]:
    return sorted(_STRATEGY_REGISTRY.keys())


def build_strategy(
    mode: str,
    llm: "LLMDialogClient",
    config: FSMConfig,
    ctx: DialogContext,
    request: object | None = None,
) -> "BaseDialogStrategy":
    cls = _STRATEGY_REGISTRY.get(mode)
    if cls is None:
        raise ValueError(f"Unknown dialog mode '{mode}'. Available: {available_modes()}")
    return cls(llm=llm, config=config, ctx=ctx, request=request)


# ==== BASE STRATEGY ====


class BaseDialogStrategy(ABC):
    """
    Shared lifecycle and cancel-flow for all strategies.

    Abstract methods: on_init, on_user_turn, succeeded, current_data.
    Optional overrides: current_phase, turn_count, on_finish, _frame_or_none.
    """

    def __init__(
        self,
        llm: "LLMDialogClient",
        config: FSMConfig,
        ctx: DialogContext,
        request: object | None = None,
    ):
        self._llm = llm
        self._config = config
        self._ctx = ctx
        self._request = request
        self._awaiting_cancel_confirmation = False
        self._user_cancelled = False

    @abstractmethod
    def on_init(self, task: str) -> str: ...

    @abstractmethod
    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]: ...

    @abstractmethod
    def succeeded(self) -> bool: ...

    @abstractmethod
    def current_data(self) -> dict: ...

    def current_phase(self) -> str:
        return "running"

    def turn_count(self) -> int:
        return 0

    def on_finish(self, success: bool) -> None:
        return None

    # ==== CANCEL FLOW ====

    def _cancel_pre_check(
        self, task: str, user_text: str, strict: bool = False
    ) -> tuple[str, bool] | None:
        """
        Intercept cancel flow before normal turn processing.
        Returns (reply, done) when active, None otherwise.

        strict=True suppresses ambiguous matches — used when the user is
        answering a closed-choice question where cancel-like words are routine.
        """
        if self._awaiting_cancel_confirmation:
            if self._llm.detect_cancel_confirmation(user_text, self._ctx):
                self._user_cancelled = True
                reply = self._llm.cancel_confirmed_response(task, self._frame_or_none(), self._ctx)
                return reply, True
            self._awaiting_cancel_confirmation = False
            reply = self._llm.cancel_denied_response(task, self._frame_or_none(), self._ctx)
            return reply, False

        if self._llm.detect_cancel_intent(user_text, self._ctx, strict=strict):
            self._awaiting_cancel_confirmation = True
            reply = self._llm.ask_cancel_confirmation(task, self._ctx)
            return reply, False

        return None

    def _frame_or_none(self) -> DialogFrame | None:
        return None
