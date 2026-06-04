"""Simulation gesture manager driving poses via JointState messages.

Selects conversational/idle poses based on /is_speaking and /target_pose,
interpolates between them, and publishes the result on /pose_tester_joints
for RViz visualization. Use arm_gesture_manager for the real robot.
"""

import os
import yaml
import random
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy, ReliabilityPolicy
from std_msgs.msg import Bool, String
from sensor_msgs.msg import JointState


class GestureManagerNode(Node):
    """Simulation-only gesture manager.

    Publishes JointState to /pose_tester_joints so that joint_state_publisher_gui
    and RViz can visualise the poses. For the real robot use arm_gesture_manager.
    """

    def __init__(self):
        super().__init__("gesture_manager_node")

        self.declare_parameter("poses_file", "nao_saved_poses.yaml")
        self.declare_parameter("transition_speed", 0.03)
        self.declare_parameter("idle_interval", 3.0)
        self.declare_parameter("hold_time_min", 1.0)
        self.declare_parameter("hold_time_max", 2.5)

        self.poses, self.pose_speeds = self._load_poses()

        self.default_speed = self.get_parameter("transition_speed").value
        self.current_speed = self.default_speed
        self._hold_min = self.get_parameter("hold_time_min").value
        self._hold_max = self.get_parameter("hold_time_max").value
        self._hold_duration = 0.0
        self._hold_start = None

        self.current_joints = self.poses.get("natural_rest", {})
        self.target_joints = self.current_joints.copy()
        self.current_pose_name = "natural_rest"

        self.is_speaking = False
        self.override_pose = ""

        self.talking_poses = [
            "open_explanation",
            "wide_explanation",
            "one_hand_explanation",
            "speaking_emphasis",
            "offer_show",
            "strong_affirmation",
        ]
        self.idle_poses = ["active_listening", "natural_rest"]

        qos_transient = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.create_subscription(Bool, "/is_speaking", self._speaking_cb, 10)
        self.create_subscription(String, "/target_pose", self._target_pose_cb, qos_transient)

        self.joint_pub = self.create_publisher(JointState, "/pose_tester_joints", 10)

        self.create_timer(0.05, self._interpolation_loop)
        self.create_timer(self.get_parameter("idle_interval").value, self._idle_behavior_loop)

    def _load_poses(self):
        file_path = self.get_parameter("poses_file").value
        if not os.path.exists(file_path):
            self.get_logger().error(f"Poses file not found: {file_path}")
            return {}, {}
        with open(file_path, "r") as f:
            raw = yaml.safe_load(f) or {}
        speeds = raw.pop("_speeds", {})
        return raw, speeds

    def _speaking_cb(self, msg: Bool):
        started_speaking = msg.data and not self.is_speaking
        self.is_speaking = msg.data

        if started_speaking and not self.override_pose:
            self._hold_start = None
            self._set_target("speech_transition")
        elif not self.is_speaking and not self.override_pose:
            self._hold_start = None
            self._set_target("active_listening")

    def _target_pose_cb(self, msg: String):
        name = msg.data
        if name == "AUTO":
            self.override_pose = ""
            self._hold_start = None
            self._set_target("natural_rest")
        elif name in self.poses:
            self.override_pose = name
            self._hold_start = None
            self._set_target(name)
        else:
            self.get_logger().warn(f'Unknown pose: "{name}"')

    def _set_target(self, pose_name: str):
        if pose_name not in self.poses:
            return
        self.current_pose_name = pose_name
        self.current_speed = self.pose_speeds.get(pose_name, self.default_speed)
        for joint, value in self.poses[pose_name].items():
            self.target_joints[joint] = value

    def _next_talking_pose(self):
        available = [
            p for p in self.talking_poses if p in self.poses and p != self.current_pose_name
        ]
        if not available:
            available = [p for p in self.talking_poses if p in self.poses]
        return random.choice(available) if available else None

    def _idle_behavior_loop(self):
        if self.override_pose or self.is_speaking:
            return
        if random.random() > 0.7:
            candidates = [p for p in self.idle_poses if p in self.poses]
            if candidates:
                self._hold_start = None
                self._set_target(random.choice(candidates))

    def _interpolation_loop(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        arrived = True

        for joint, target_val in self.target_joints.items():
            current_val = self.current_joints.get(joint, target_val)
            diff = target_val - current_val

            if abs(diff) > self.current_speed:
                self.current_joints[joint] = current_val + (
                    self.current_speed if diff > 0 else -self.current_speed
                )
                arrived = False
            else:
                self.current_joints[joint] = target_val

            msg.name.append(joint)
            msg.position.append(self.current_joints[joint])

        self.joint_pub.publish(msg)

        if not self.is_speaking or self.override_pose or not arrived:
            return

        now = self.get_clock().now()

        if self._hold_start is None:
            self._hold_duration = random.uniform(self._hold_min, self._hold_max)
            self._hold_start = now
            return

        elapsed = (now - self._hold_start).nanoseconds / 1e9
        if elapsed < self._hold_duration:
            return

        self._hold_start = None

        if self.current_pose_name == "speech_transition":
            next_pose = self._next_talking_pose()
            if next_pose:
                self._set_target(next_pose)
        else:
            self._set_target("speech_transition")


def main(args=None):
    rclpy.init(args=args)
    node = GestureManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
