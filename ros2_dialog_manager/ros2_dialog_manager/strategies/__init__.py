"""
Dialog strategies package.

Importing this module automatically registers all bundled strategies.
To add a new strategy:
  1. Create the file with a class decorated with @register_strategy("mode").
  2. Add the import here.
"""

# Register the strategies on package import.
from .slot_filling import SlotFillingStrategy  # noqa: F401
from .explanation import ExplanationStrategy  # noqa: F401
from .quiz import QuizStrategy  # noqa: F401

# Public package API.
from .base import (  # noqa: F401
    BaseDialogStrategy,
    FSMConfig,
    OpKind,
    Operation,
    available_modes,
    build_strategy,
    register_strategy,
)
