# Launch the generic audio bridge on a device with a mic/speaker (e.g. a robot
# head). Pair it with the speech nodes running in "topic" mode elsewhere.

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_params = os.path.join(
        get_package_share_directory("speech_io"), "config", "audio_bridge.yaml"
    )

    params_arg = DeclareLaunchArgument("params", default_value=default_params)
    params = LaunchConfiguration("params")

    return LaunchDescription(
        [
            params_arg,
            Node(
                package="speech_io",
                executable="audio_bridge_node",
                name="audio_bridge_node",
                output="screen",
                parameters=[params],
            ),
        ]
    )
