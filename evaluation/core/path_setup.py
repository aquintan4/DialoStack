"""
Adds the production dialog manager package to sys.path so that evaluation
scripts can import it without ROS being sourced.

Call setup_path() before any import from ros2_dialog_manager.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Path to the ROS package directory that contains ros2_dialog_manager/
_DIALOG_MGR_PKG = os.path.normpath(os.path.join(_HERE, "..", "..", "ros2_dialog_manager"))


def setup_path() -> None:
    if _DIALOG_MGR_PKG not in sys.path:
        sys.path.insert(0, _DIALOG_MGR_PKG)


def load_config(config_path: str | None = None) -> dict:
    import yaml

    path = config_path or os.path.join(_HERE, "..", "config.yaml")
    with open(os.path.abspath(path), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompts(prompts_yaml_path: str) -> dict[str, str]:
    import yaml

    with open(os.path.abspath(prompts_yaml_path), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["dialog_manager_node"]["ros__parameters"]["prompts"]


def resolve_path(relative_to_eval: str) -> str:
    eval_root = os.path.normpath(os.path.join(_HERE, ".."))
    return os.path.normpath(os.path.join(eval_root, relative_to_eval))
