"""Saves the current joint state to a YAML file when triggered.

Listens on /joint_states for the live pose and on /save_pose_trigger for a
pose name, then writes (or updates) that named pose in nao_saved_poses.yaml.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String
import yaml
import os


class PoseSaver(Node):
    def __init__(self):
        super().__init__("pose_saver")
        self.current_joints = {}

        self.joint_sub = self.create_subscription(
            JointState, "/joint_states", self.joint_callback, 10
        )

        qos_profile = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

        self.trigger_sub = self.create_subscription(
            String, "/save_pose_trigger", self.trigger_callback, qos_profile
        )

    def joint_callback(self, msg):
        for name, position in zip(msg.name, msg.position):
            self.current_joints[name] = position

    def trigger_callback(self, msg):
        pose_name = msg.data
        if not self.current_joints:
            return

        file_path = "nao_saved_poses.yaml"
        data = {}

        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                data = yaml.safe_load(f) or {}

        is_update = pose_name in data
        data[pose_name] = self.current_joints

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        if is_update:
            self.get_logger().info(f"Pose '{pose_name}' updated successfully.")
        else:
            self.get_logger().info(f"New pose '{pose_name}' saved.")


def main(args=None):
    rclpy.init(args=args)
    node = PoseSaver()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
