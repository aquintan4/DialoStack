# Launch the speech-to-text and text-to-speech nodes with shared parameters.

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_params = os.path.join(get_package_share_directory("speech_io"), "config", "params.yaml")

    params_arg = DeclareLaunchArgument("params", default_value=default_params)
    params = LaunchConfiguration("params")

    return LaunchDescription(
        [
            params_arg,
            Node(
                package="speech_io",
                executable="speech_to_text_node",
                name="speech_to_text_node",
                output="screen",
                parameters=[params],
            ),
            Node(
                package="speech_io",
                executable="text_to_speech_node",
                name="text_to_speech_node",
                output="screen",
                parameters=[params],
            ),
        ]
    )
