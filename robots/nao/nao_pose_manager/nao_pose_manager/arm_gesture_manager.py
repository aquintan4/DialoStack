"""Arm gesture manager for the real NAO robot.

Selects conversational/idle arm poses based on /is_speaking and /target_pose,
interpolates between them, and drives the arm joints through the nao_lola
effector topics. A simple FSM cycles between a neutral speech-ready pose and
talking gestures while the robot speaks.
"""

import os
import yaml
import random
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy, ReliabilityPolicy
from std_msgs.msg import Bool, String
from nao_lola_command_msgs.msg import JointPositions, JointStiffnesses

# Arm joint name → nao_lola index (head and legs intentionally excluded)
ARM_JOINT_INDEXES = {
    "LShoulderPitch": 2,
    "LShoulderRoll": 3,
    "LElbowYaw": 4,
    "LElbowRoll": 5,
    "LWristYaw": 6,
    "RShoulderPitch": 18,
    "RShoulderRoll": 19,
    "RElbowYaw": 20,
    "RElbowRoll": 21,
    "RWristYaw": 22,
    "LHand": 23,
    "RHand": 24,
}

TALKING_POSES = [
    "open_explanation",
    "wide_explanation",
    "one_hand_explanation",
    "speaking_emphasis",
    "offer_show",
    "strong_affirmation",
]

IDLE_POSES = ["active_listening", "natural_rest"]

# Neutral speech-ready pose. The robot enters this between gestures so that
# each gesture is clearly distinct and the motion looks deliberate.
SPEECH_TRANSITION_POSE = "speech_transition"


class ArmGestureManagerNode(Node):
    def __init__(self):
        super().__init__("arm_gesture_manager")

        self.declare_parameter("poses_file", "")
        self.declare_parameter("transition_speed", 0.03)
        self.declare_parameter("idle_interval", 3.0)
        # Hold time is sampled uniformly from [hold_time_min, hold_time_max]
        # each time the robot arrives at a pose, so gestures feel natural and
        # unpredictable rather than metronomic.
        self.declare_parameter("hold_time_min", 1.0)
        self.declare_parameter("hold_time_max", 2.5)
        self.declare_parameter("stiffness", 0.8)

        self.poses, self.pose_speeds = self._load_poses()

        self.default_speed = self.get_parameter("transition_speed").value
        self.current_speed = self.default_speed
        self._hold_min = self.get_parameter("hold_time_min").value
        self._hold_max = self.get_parameter("hold_time_max").value
        self._hold_duration = 0.0  # sampled each time we arrive at a pose
        self._hold_start = None

        init_pose = self.poses.get("natural_rest", {})
        self.current_joints = {j: init_pose.get(j, 0.0) for j in ARM_JOINT_INDEXES}
        self.target_joints = self.current_joints.copy()
        self.current_pose_name = "natural_rest"

        self.is_speaking = False
        self.override_pose = ""
        self.stiffness_value = self.get_parameter("stiffness").value
        self._configured_stiffness = self.stiffness_value
        self._gestures_enabled = True

        qos_transient = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.create_subscription(Bool, "/is_speaking", self._speaking_cb, 10)
        self.create_subscription(String, "/target_pose", self._target_pose_cb, qos_transient)

        self._pos_pub = self.create_publisher(JointPositions, "/effectors/joint_positions", 10)
        self._stiff_pub = self.create_publisher(
            JointStiffnesses, "/effectors/joint_stiffnesses", 10
        )

        self.create_timer(0.05, self._interpolation_loop)
        self.create_timer(1.0, self._publish_stiffness)
        self.create_timer(
            self.get_parameter("idle_interval").value,
            self._idle_behavior_loop,
        )

        self.get_logger().info(
            f"ArmGestureManager ready — {len(self.poses)} poses, "
            f"hold_time=[{self._hold_min}, {self._hold_max}]s, speed={self.default_speed}"
        )

    # ==== POSE LOADING ====

    def _load_poses(self):
        file_path = self.get_parameter("poses_file").value
        if not file_path or not os.path.exists(file_path):
            self.get_logger().error(f'poses_file not found: "{file_path}"')
            return {}, {}

        with open(file_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        speeds = raw.pop("_speeds", {})

        poses = {}
        for name, joints in raw.items():
            arm_only = {j: float(v) for j, v in joints.items() if j in ARM_JOINT_INDEXES}
            if arm_only:
                poses[name] = arm_only

        self.get_logger().info(f"Poses loaded: {sorted(poses.keys())}")
        return poses, speeds

    # ==== STIFFNESS (republished every second to keep motors active) ====

    def _publish_stiffness(self):
        msg = JointStiffnesses()
        msg.indexes = list(ARM_JOINT_INDEXES.values())
        msg.stiffnesses = [self.stiffness_value] * len(ARM_JOINT_INDEXES)
        self._stiff_pub.publish(msg)

    # ==== SUBSCRIPTION CALLBACKS ====

    def _speaking_cb(self, msg: Bool):
        started_speaking = msg.data and not self.is_speaking
        self.is_speaking = msg.data

        if started_speaking and not self.override_pose:
            self._hold_start = None
            self._set_target(SPEECH_TRANSITION_POSE)
        elif not self.is_speaking and not self.override_pose:
            self._hold_start = None
            self._set_target("active_listening")

    def _target_pose_cb(self, msg: String):
        name = msg.data
        if name == "FREE":
            # Disable all gesticulation: joints go limp (stiffness 0) so the robot
            # can be moved externally (e.g. during guided exercises) without fighting
            # the gesture manager. Position publishing also stops.
            self._gestures_enabled = False
            self.override_pose = ""
            self.stiffness_value = 0.0
            self.get_logger().info("Gestures DISABLED — arm joints free")
        elif name == "AUTO":
            self._gestures_enabled = True
            self.stiffness_value = self._configured_stiffness
            self.override_pose = ""
            self._hold_start = None
            self._set_target("natural_rest")
            self.get_logger().info("Gestures ENABLED — returning to AUTO mode")
        elif name in self.poses:
            self._gestures_enabled = True
            self.stiffness_value = self._configured_stiffness
            self.override_pose = name
            self._hold_start = None
            self._set_target(name)
        else:
            self.get_logger().warn(f'Unknown pose requested: "{name}"')

    # ==== POSE CONTROL ====

    def _set_target(self, pose_name: str):
        if pose_name not in self.poses:
            return
        self.current_pose_name = pose_name
        self.current_speed = self.pose_speeds.get(pose_name, self.default_speed)
        for joint, value in self.poses[pose_name].items():
            self.target_joints[joint] = value

    def _next_talking_pose(self):
        available = [p for p in TALKING_POSES if p in self.poses and p != self.current_pose_name]
        if not available:
            available = [p for p in TALKING_POSES if p in self.poses]
        return random.choice(available) if available else None

    def _idle_behavior_loop(self):
        if not self._gestures_enabled or self.override_pose or self.is_speaking:
            return
        if random.random() > 0.7:
            candidates = [p for p in IDLE_POSES if p in self.poses]
            if candidates:
                self._hold_start = None
                self._set_target(random.choice(candidates))

    # ==== INTERPOLATION AND PUBLISH LOOP (20 Hz) ====

    def _interpolation_loop(self):
        if not self._gestures_enabled:
            return

        arrived = True

        for joint in ARM_JOINT_INDEXES:
            target = self.target_joints.get(joint, self.current_joints.get(joint, 0.0))
            current = self.current_joints.get(joint, target)
            diff = target - current

            if abs(diff) > self.current_speed:
                self.current_joints[joint] = current + (
                    self.current_speed if diff > 0 else -self.current_speed
                )
                arrived = False
            else:
                self.current_joints[joint] = target

        msg = JointPositions()
        msg.indexes = list(ARM_JOINT_INDEXES.values())
        msg.positions = [float(self.current_joints[j]) for j in ARM_JOINT_INDEXES]
        self._pos_pub.publish(msg)

        if not self.is_speaking or self.override_pose:
            return

        if not arrived:
            return  # still moving, nothing to decide yet

        now = self.get_clock().now()

        # First tick after arriving: sample a random hold duration and start timer
        if self._hold_start is None:
            self._hold_duration = random.uniform(self._hold_min, self._hold_max)
            self._hold_start = now
            return

        elapsed = (now - self._hold_start).nanoseconds / 1e9
        if elapsed < self._hold_duration:
            return

        # Hold expired — advance to the next pose
        self._hold_start = None

        if self.current_pose_name == SPEECH_TRANSITION_POSE:
            # Ready: enter the first gesture
            next_pose = self._next_talking_pose()
            if next_pose:
                self._set_target(next_pose)
        else:
            # After each gesture, return to the neutral speech position so that
            # each gesture starts from the same baseline and looks deliberate.
            self._set_target(SPEECH_TRANSITION_POSE)


def main(args=None):
    rclpy.init(args=args)
    node = ArmGestureManagerNode()
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
