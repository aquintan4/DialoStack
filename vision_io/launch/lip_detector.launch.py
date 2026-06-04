# Launch the lip activity detector node with its parameter file.

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory("vision_io"), "config", "lip_activity_params.yaml"
    )

    return LaunchDescription(
        [
            Node(
                package="vision_io",
                executable="lip_activity_detector",
                name="lip_activity_detector_node",
                parameters=[config],
                output="screen",
            )
        ]
    )
