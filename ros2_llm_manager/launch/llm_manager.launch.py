"""Launch file for the LLM Manager node with a configurable params file."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("ros2_llm_manager")
    default_params = os.path.join(pkg_share, "config", "params.yaml")

    params_arg = DeclareLaunchArgument("params", default_value=default_params)
    params = LaunchConfiguration("params")

    return LaunchDescription(
        [
            params_arg,
            Node(
                package="ros2_llm_manager",
                executable="llm_manager_node",
                name="llm_manager_node",
                output="screen",
                parameters=[params],
            ),
        ]
    )
