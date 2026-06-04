# Copyright 2021 Kenji Brameld
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            declare_launch_argument(),
            robot_state_publisher(),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    os.path.join(
                        get_package_share_directory("nao_description"), "rviz", "nao.rviz"
                    ),
                ],
            ),
            Node(package="nao_description", executable="zero_joint_state_publisher"),
        ]
    )


def declare_launch_argument():
    return DeclareLaunchArgument(
        "use_sim_time", default_value="false", description="Use simulation (Gazebo) clock if true"
    )


def robot_state_publisher():

    use_sim_time = LaunchConfiguration("use_sim_time", default="true")

    urdf_file_name = "nao.urdf"
    urdf = os.path.join(get_package_share_directory("nao_description"), "urdf", urdf_file_name)
    with open(urdf, "r") as infp:
        robot_desc = infp.read()

    return Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{"use_sim_time": use_sim_time, "robot_description": robot_desc}],
        arguments=[urdf],
    )
