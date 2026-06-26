"""Run the example tree with the generic BT runner."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('dialostack_bt_client')
    bt_xml = os.path.join(pkg, 'config', 'example.xml')

    return LaunchDescription([
        Node(
            package='dialostack_bt_client',
            executable='bt_runner',
            name='dialostack_bt_runner',
            output='screen',
            parameters=[{'bt_xml': bt_xml}],
        ),
    ])
