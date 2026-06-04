"""
BaseProvider — abstract contract for all LLM backends.

Every provider must implement four methods:
  connect()          → validate credentials / reachability.
  ensure_model_ready() → pre-warm the model so the first inference has no
                         cold-start penalty (no-op for cloud providers).
  generate()         → run inference, optionally streaming tokens.
  close()            → release resources cleanly.

GenerateResult is the single return type for generate(); the node never
touches provider-specific response objects.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class GenerateResult:
    """Normalised inference result, provider-agnostic."""

    success: bool
    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""


class BaseProvider(ABC):

    # Subclasses set this so the node can fall back to a sensible default
    # without knowing provider internals.
    default_model: str = ""

    @abstractmethod
    def connect(self) -> tuple[bool, str]:
        """Establish connection and validate credentials."""
        pass

    @abstractmethod
    def ensure_model_ready(self, model: str) -> tuple[bool, str]:
        """Pre-warm the model to avoid cold-start latency on first inference."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release resources (HTTP connections, client handles, …)."""
        pass

    @abstractmethod
    def generate(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 0,
        format_schema: Optional[dict] = None,
        stream_callback: Optional[Callable[[str], bool]] = None,
    ) -> GenerateResult:
        """
        Run inference.

        stream_callback, when provided, is called with each token as it
        arrives. Returning False from the callback signals cancellation;
        the provider should stop generation and return a result with
        error="cancelled".
        """
        pass
