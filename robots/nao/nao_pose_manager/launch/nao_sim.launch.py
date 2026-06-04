# Simulation bringup: robot_state_publisher, RViz, and the pose tooling nodes.

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_nao_description = get_package_share_directory("nao_description")
    pkg_pose_manager = get_package_share_directory("nao_pose_manager")

    urdf_file = os.path.join(pkg_nao_description, "urdf", "nao.urdf")
    rviz_config = os.path.join(pkg_pose_manager, "config", "config.rviz")

    robot_desc = ParameterValue(Command(["xacro ", urdf_file]), value_type=str)

    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                name="robot_state_publisher",
                parameters=[{"robot_description": robot_desc}],
            ),
            Node(
                package="joint_state_publisher_gui",
                executable="joint_state_publisher_gui",
                name="joint_state_publisher_gui",
                # Listen to the tester topic so the sliders stay in sync
                parameters=[{"source_list": ["/pose_tester_joints"]}],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz2",
                arguments=["-d", rviz_config],  # Load the saved view
                output="screen",
            ),
            Node(package="nao_pose_manager", executable="pose_saver", name="pose_saver"),
            Node(package="nao_pose_manager", executable="gui_trigger", name="gui_trigger"),
            Node(package="nao_pose_manager", executable="pose_tester", name="pose_tester"),
            Node(
                package="nao_pose_manager",
                executable="gesture_manager",
                name="gesture_manager",
                parameters=[
                    {"poses_file": os.path.join(pkg_pose_manager, "config", "nao_saved_poses.yaml")}
                ],
            ),
        ]
    )
