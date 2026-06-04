# Launch the arm gesture manager and eye LED feedback nodes for the real NAO.

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("nao_pose_manager")
    default_poses = os.path.join(pkg, "config", "nao_saved_poses.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "poses_file",
                default_value=default_poses,
                description="Path to the YAML file with the saved poses",
            ),
            DeclareLaunchArgument(
                "transition_speed",
                default_value="0.05",
                description="Interpolation speed between poses (rad/tick at 20 Hz)",
            ),
            DeclareLaunchArgument(
                "idle_interval",
                default_value="3.0",
                description="Interval in seconds between idle pose changes",
            ),
            DeclareLaunchArgument(
                "hold_time_min",
                default_value="1.0",
                description="Minimum seconds to hold a gesture",
            ),
            DeclareLaunchArgument(
                "hold_time_max",
                default_value="2.5",
                description="Maximum seconds to hold a gesture",
            ),
            DeclareLaunchArgument(
                "stiffness",
                default_value="0.8",
                description="Arm motor stiffness (0.0 – 1.0)",
            ),
            Node(
                package="nao_pose_manager",
                executable="arm_gesture_manager",
                name="arm_gesture_manager",
                output="screen",
                parameters=[
                    {
                        "poses_file": LaunchConfiguration("poses_file"),
                        "transition_speed": LaunchConfiguration("transition_speed"),
                        "idle_interval": LaunchConfiguration("idle_interval"),
                        "hold_time_min": LaunchConfiguration("hold_time_min"),
                        "hold_time_max": LaunchConfiguration("hold_time_max"),
                        "stiffness": LaunchConfiguration("stiffness"),
                    }
                ],
            ),
            Node(
                package="nao_pose_manager",
                executable="eye_led_feedback",
                name="eye_led_feedback",
                output="screen",
            ),
        ]
    )
