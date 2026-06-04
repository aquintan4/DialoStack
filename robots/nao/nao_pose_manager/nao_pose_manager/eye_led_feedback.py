"""Drives the NAO eye LEDs to give subtle interaction feedback.

Maps interaction state to eye color: warm-white pulse while the robot speaks
(/is_speaking), green scaled by user voice activity (/user_vad), and dim blue
when idle. Colors fade smoothly between states.
"""

import math
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy, ReliabilityPolicy
from std_msgs.msg import Bool, Float32, ColorRGBA
from nao_lola_command_msgs.msg import LeftEyeLeds, RightEyeLeds

# Base colors (r, g, b) — kept intentionally dim for subtlety
_IDLE = (0.00, 0.15, 0.60)  # dim blue    — "ready, waiting"
_USER_VAD = (0.05, 0.65, 0.15)  # green       — "I hear you" (scaled by VAD)
_ROBOT_SPEAK = (0.80, 0.80, 0.55)  # warm white  — "I'm talking"

_FADE = 0.12  # interpolation step per tick (10 Hz → ~1 s to full transition)
_PULSE_HZ = 0.7  # pulse frequency while robot speaks
_PULSE_AMP = 0.20  # ±brightness of the pulse
_VAD_THRESH = 0.35  # minimum VAD to consider user speaking
_VAD_SMOOTH = 0.3  # low-pass weight for VAD (avoids flicker)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class EyeLedFeedbackNode(Node):
    """Publishes eye LED colors to give the user subtle interaction feedback.

    States (priority order):
      1. robot_speaking  — /is_speaking = True
      2. user_speaking   — /user_vad above threshold (and robot not speaking)
      3. idle            — default
    """

    def __init__(self):
        super().__init__("eye_led_feedback")

        self.declare_parameter("vad_threshold", _VAD_THRESH)
        self.declare_parameter("pulse_hz", _PULSE_HZ)
        self.declare_parameter("pulse_amp", _PULSE_AMP)
        self.declare_parameter("fade_speed", _FADE)

        self._vad_thresh = self.get_parameter("vad_threshold").value
        self._pulse_hz = self.get_parameter("pulse_hz").value
        self._pulse_amp = self.get_parameter("pulse_amp").value
        self._fade = self.get_parameter("fade_speed").value

        self._robot_speaking = False
        self._vad_raw = 0.0
        self._vad_smooth = 0.0
        self._phase = 0.0  # pulse phase accumulator (radians)
        self._current = list(_IDLE)  # [r, g, b] currently displayed

        qos_transient = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.create_subscription(Bool, "/is_speaking", self._speaking_cb, qos_transient)
        self.create_subscription(Float32, "/user_vad", self._vad_cb, 10)

        self._left_pub = self.create_publisher(LeftEyeLeds, "/effectors/left_eye_leds", 10)
        self._right_pub = self.create_publisher(RightEyeLeds, "/effectors/right_eye_leds", 10)

        self.create_timer(0.1, self._update)

        self.get_logger().info("EyeLedFeedback ready")

    # ==== CALLBACKS ====

    def _speaking_cb(self, msg: Bool):
        self._robot_speaking = msg.data

    def _vad_cb(self, msg: Float32):
        # Exponential low-pass to smooth out short bursts
        self._vad_smooth = (1.0 - _VAD_SMOOTH) * self._vad_smooth + _VAD_SMOOTH * msg.data

    # ==== MAIN UPDATE (10 Hz) ====

    def _update(self):
        dt = 0.1

        # 1 — Determine target color
        if self._robot_speaking:
            # Warm white with a slow pulse
            self._phase += 2.0 * math.pi * self._pulse_hz * dt
            pulse = 1.0 + self._pulse_amp * math.sin(self._phase)
            target = [min(1.0, c * pulse) for c in _ROBOT_SPEAK]

        elif self._vad_smooth > self._vad_thresh:
            # Green scaled by how strongly the user is speaking
            intensity = min(
                1.0, (self._vad_smooth - self._vad_thresh) / (1.0 - self._vad_thresh) + 0.5
            )
            target = [c * intensity for c in _USER_VAD]
            self._phase = 0.0

        else:
            target = list(_IDLE)
            self._phase = 0.0

        # 2 — Interpolate toward target
        self._current = [_lerp(self._current[i], target[i], self._fade) for i in range(3)]

        # 3 — Publish
        r, g, b = self._current
        color = ColorRGBA(r=float(r), g=float(g), b=float(b), a=1.0)

        left_msg = LeftEyeLeds()
        right_msg = RightEyeLeds()
        left_msg.colors = [color] * 8
        right_msg.colors = [color] * 8

        self._left_pub.publish(left_msg)
        self._right_pub.publish(right_msg)


def main(args=None):
    rclpy.init(args=args)
    node = EyeLedFeedbackNode()
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
