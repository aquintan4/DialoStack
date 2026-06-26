# Launch file: brings up the speech I/O, LLM manager and dialog manager nodes
# with the shared app_params.yaml (and prompts.yaml for the dialog manager).

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory("ros2_dialog_manager")
    app_params = os.path.join(pkg_dir, "config", "app_params.yaml")
    prompts = os.path.join(pkg_dir, "config", "prompts.yaml")

    for f in (app_params, prompts):
        if not os.path.isfile(f):
            raise FileNotFoundError(f"Config not found: {f}")

    # When launched from the GUI, DIALOSTACK_GUI_PARAMS points to a temporary
    # YAML file generated from the Config Editor. It is applied after app_params
    # so its values take precedence (ROS 2 applies params files in order).
    gui_override = os.environ.get("DIALOSTACK_GUI_PARAMS", "")
    extra = [gui_override] if gui_override and os.path.isfile(gui_override) else []

    return LaunchDescription(
        [
            Node(
                package="speech_io",
                executable="speech_to_text_node",
                name="speech_to_text_node",
                output="screen",
                parameters=[app_params] + extra,
            ),
            Node(
                package="speech_io",
                executable="text_to_speech_node",
                name="text_to_speech_node",
                output="screen",
                parameters=[app_params] + extra,
            ),
            Node(
                package="ros2_llm_manager",
                executable="llm_manager_node",
                name="llm_manager_node",
                output="screen",
                parameters=[app_params] + extra,
            ),
            Node(
                package="ros2_dialog_manager",
                executable="dialog_manager_node",
                name="dialog_manager_node",
                output="screen",
                parameters=[app_params, prompts] + extra,
            ),
        ]
    )
