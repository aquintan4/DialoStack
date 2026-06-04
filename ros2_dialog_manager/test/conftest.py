"""Pytest configuration: make the package importable without a colcon install."""

import os
import sys

# Allow running pytest from the package root without a full colcon install.
_pkg_root = os.path.join(os.path.dirname(__file__), "..")
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)
