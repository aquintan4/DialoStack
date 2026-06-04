"""
LipActivityDetectorNode — ROS2 node that detects lip movement to classify
whether the user is speaking, using MediaPipe FaceLandmarker (Tasks API).

The detector computes the variance of consecutive lip-gap differences
(roughness) over a short rolling window. Speech produces rapid up-down
oscillations that sustain high roughness; a single mouth opening or smile
produces a monotonic movement whose roughness drops quickly once the mouth
reaches its new position.

Topics published:
  /user_speaking   (Bool)    — True while speaking is detected.
  /lip_activity    (Float32) — raw lip-gap ratio (normalised by face height).

Topics consumed:
  /camera/image_raw  (sensor_msgs/Image)
"""

import collections
import os
import threading
import time
import urllib.request

import cv2
import numpy as np
import rclpy
import mediapipe as mp

from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Float32
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ==== LANDMARK INDICES ====

_UPPER_LIP = 13
_LOWER_LIP = 14
_NOSE_TIP = 4
_CHIN = 152

_LIP_OUTLINE = [
    61,
    185,
    40,
    39,
    37,
    0,
    267,
    269,
    270,
    409,
    291,
    375,
    321,
    405,
    314,
    17,
    84,
    181,
    91,
    146,
    61,
]

_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
_MODEL_PATH = "/tmp/face_landmarker.task"


def _ensure_model() -> str:
    if not os.path.exists(_MODEL_PATH):
        print(f"[lip_activity_detector] Downloading model to {_MODEL_PATH} ...")
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        print("[lip_activity_detector] Download complete.")
    return _MODEL_PATH


# ==== LIP ACTIVITY FSM ====


class _LipFSM:
    """
    SILENT → SPEAKING : variance of consecutive lip-gap diffs over the last
                        window_frames exceeds roughness_threshold.
                        Speech: rapid oscillations → high variance.
                        Yawn/smile: sustained plateau → diffs ≈ 0 → ~zero variance.
    SPEAKING → SILENT : variance stays below threshold for silence_secs.
    """

    SILENT = "SILENT"
    SPEAKING = "SPEAKING"

    def __init__(
        self, roughness_threshold: float, onset_secs: float, window_frames: int, silence_secs: float
    ) -> None:
        self.roughness_threshold = roughness_threshold
        self.onset_secs = onset_secs
        self.silence_secs = silence_secs
        self.state = self.SILENT
        self._buf: collections.deque = collections.deque(maxlen=window_frames)
        self._active_since: float | None = None
        self._below_since: float | None = None
        self.last_roughness = 0.0

    def update(self, ratio: float) -> tuple[str, bool]:
        """Feed the smoothed lip-gap ratio; returns (new_state, state_changed)."""
        now = time.monotonic()
        prev = self.state

        self._buf.append(ratio)
        if len(self._buf) >= 4:
            self.last_roughness = float(np.var(np.diff(np.array(self._buf))))
        else:
            self.last_roughness = 0.0

        active = self.last_roughness >= self.roughness_threshold

        if self.state == self.SILENT:
            if active:
                if self._active_since is None:
                    self._active_since = now
                elif now - self._active_since >= self.onset_secs:
                    self.state = self.SPEAKING
                    self._below_since = None
            else:
                self._active_since = None
        else:
            if not active:
                if self._below_since is None:
                    self._below_since = now
                elif now - self._below_since >= self.silence_secs:
                    self.state = self.SILENT
                    self._active_since = None
            else:
                self._below_since = None

        return self.state, self.state != prev


# ==== ROS2 NODE ====


class LipActivityDetectorNode(Node):

    def __init__(self):
        super().__init__("lip_activity_detector")

        self._declare_parameters()
        self._read_parameters()

        self._bridge = CvBridge()

        model_path = _ensure_model()
        base_opts = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=self._min_detection_conf,
            min_tracking_confidence=self._min_tracking_conf,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self._frame_ts_ms = 0

        self._window: collections.deque[float] = collections.deque(maxlen=self._smoothing_frames)
        self._fsm = _LipFSM(
            self._roughness_threshold, self._onset_secs, self._roughness_window, self._silence_secs
        )
        self._fsm_lock = threading.Lock()

        self._baseline = 0.0
        self._baseline_window: collections.deque = collections.deque(maxlen=200)

        self._speaking_state = False
        self._state_lock = threading.Lock()

        qos_best = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.create_subscription(Image, self._image_topic, self._on_image, qos_best)

        self._pub_speaking = self.create_publisher(Bool, self._speaking_topic, 10)
        self._pub_ratio = self.create_publisher(Float32, self._activity_topic, 10)

        if self._show_debug:
            cv2.namedWindow("Lip Activity — debug", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Lip Activity — debug", 640, 480)

        self.get_logger().info(
            f"LipActivityDetector ready — "
            f"roughness_threshold={self._roughness_threshold:.2e}  "
            f"onset={self._onset_secs}s  silence={self._silence_secs}s  "
            f"window={self._roughness_window}fr  "
            f"debug={'ON' if self._show_debug else 'OFF'}"
        )

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("speaking_topic", "/user_speaking")
        self.declare_parameter("lip_activity_topic", "/lip_activity")
        self.declare_parameter("min_detection_confidence", 0.5)
        self.declare_parameter("min_tracking_confidence", 0.5)
        self.declare_parameter("open_threshold", 0.04)
        self.declare_parameter("smoothing_frames", 4)
        self.declare_parameter("roughness_threshold", 7e-6)
        self.declare_parameter("roughness_window", 10)
        self.declare_parameter("onset_secs", 0.90)
        self.declare_parameter("silence_secs", 1.20)
        self.declare_parameter("show_debug", False)

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self._image_topic = p("image_topic").value
        self._speaking_topic = p("speaking_topic").value
        self._activity_topic = p("lip_activity_topic").value
        self._min_detection_conf = float(p("min_detection_confidence").value)
        self._min_tracking_conf = float(p("min_tracking_confidence").value)
        self._open_threshold = float(p("open_threshold").value)
        self._smoothing_frames = int(p("smoothing_frames").value)
        self._roughness_threshold = float(p("roughness_threshold").value)
        self._roughness_window = int(p("roughness_window").value)
        self._onset_secs = float(p("onset_secs").value)
        self._silence_secs = float(p("silence_secs").value)
        raw = p("show_debug").value
        self._show_debug = raw.strip().lower() == "true" if isinstance(raw, str) else bool(raw)

    # ==== IMAGE CALLBACK ====

    def _on_image(self, msg: Image) -> None:
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"cv_bridge error: {exc}")
            return

        self._frame_ts_ms += 33
        mp_img = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = self._landmarker.detect_for_video(mp_img, self._frame_ts_ms)
        landmarks = result.face_landmarks[0] if result.face_landmarks else None
        ratio = self._mouth_openness(landmarks) if landmarks else 0.0

        self._pub_ratio.publish(Float32(data=float(ratio)))

        if ratio > 0.0:
            self._baseline_window.append(ratio)
        if self._baseline_window:
            self._baseline = float(np.percentile(self._baseline_window, 10))

        effective_thr = self._baseline + self._open_threshold
        self._window.append(ratio)
        smoothed = float(np.mean(self._window))

        with self._fsm_lock:
            lip_state, _ = self._fsm.update(smoothed)
            roughness = self._fsm.last_roughness

        speaking = lip_state == _LipFSM.SPEAKING

        with self._state_lock:
            changed = speaking != self._speaking_state
            if changed:
                self._speaking_state = speaking

        if changed:
            self._pub_speaking.publish(Bool(data=speaking))
            self.get_logger().info(
                f"{'▶ SPEAKING' if speaking else '■ SILENT'}  "
                f"roughness={roughness:.2e}  thr={self._roughness_threshold:.2e}  "
                f"ratio={ratio:.3f}  smoothed={smoothed:.3f}"
            )

        if self._show_debug:
            self._draw_debug(frame, landmarks, ratio, smoothed, effective_thr, lip_state, roughness)

    # ==== LIP OPENNESS ====

    @staticmethod
    def _mouth_openness(landmarks) -> float:
        lip_gap = abs(landmarks[_LOWER_LIP].y - landmarks[_UPPER_LIP].y)
        face_height = abs(landmarks[_CHIN].y - landmarks[_NOSE_TIP].y) + 1e-9
        return float(lip_gap / face_height)

    # ==== DEBUG DISPLAY ====

    def _draw_debug(
        self,
        frame: np.ndarray,
        landmarks,
        ratio: float,
        smoothed: float,
        effective_thr: float,
        lip_state: str,
        roughness: float,
    ) -> None:
        canvas = frame.copy()
        speaking = lip_state == _LipFSM.SPEAKING
        state_color = (0, 230, 0) if speaking else (160, 160, 160)
        lip_color = (0, 200, 255) if speaking else (100, 100, 100)

        if landmarks:
            self._draw_lip_landmarks(canvas, landmarks, lip_color)

        overlay = canvas.copy()
        cv2.rectangle(overlay, (0, 0), (440, 130), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.55, canvas, 0.45, 0, canvas)

        cv2.putText(
            canvas,
            "SPEAKING" if speaking else "SILENT",
            (12, 50),
            cv2.FONT_HERSHEY_DUPLEX,
            1.5,
            state_color,
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"LIPS: {lip_state}",
            (240, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            lip_color,
            1,
            cv2.LINE_AA,
        )

        r_color = (0, 230, 0) if roughness >= self._roughness_threshold else (120, 120, 120)
        cv2.putText(
            canvas,
            f"roughness: {roughness:.2e}  thr: {self._roughness_threshold:.2e}",
            (12, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            r_color,
            1,
            cv2.LINE_AA,
        )

        cv2.putText(
            canvas,
            f"ratio:{ratio:.3f}  smoothed:{smoothed:.3f}  base:{self._baseline:.3f}  thr:{effective_thr:.3f}",
            (12, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )
        with self._fsm_lock:
            active_since = self._fsm._active_since
        onset_elapsed = (time.monotonic() - active_since) if active_since else 0.0
        cv2.putText(
            canvas,
            f"onset={self._onset_secs}s  elapsed={onset_elapsed:.2f}s  window={self._roughness_window}fr  silence={self._silence_secs}s",
            (12, 106),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (180, 180, 255),
            1,
            cv2.LINE_AA,
        )

        bx, by, bw, bh = 12, 112, 416, 12
        scale = max(effective_thr * 3, 1e-6)
        cv2.rectangle(canvas, (bx, by), (bx + bw, by + bh), (50, 50, 50), -1)
        filled = int(min(smoothed / scale, 1.0) * bw)
        if filled > 0:
            cv2.rectangle(canvas, (bx, by), (bx + filled, by + bh), lip_color, -1)
        for val, color in [(self._baseline, (200, 200, 0)), (effective_thr, (0, 0, 220))]:
            x = bx + int(min(val / scale, 1.0) * bw)
            cv2.line(canvas, (x, by - 3), (x, by + bh + 3), color, 2)

        cv2.imshow("Lip Activity — debug", canvas)
        cv2.waitKey(1)

    @staticmethod
    def _draw_lip_landmarks(frame: np.ndarray, landmarks, color: tuple) -> None:
        h, w = frame.shape[:2]
        pts = np.array(
            [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in _LIP_OUTLINE],
            dtype=np.int32,
        )
        cv2.polylines(frame, [pts], isClosed=False, color=color, thickness=2)
        for idx in (_UPPER_LIP, _LOWER_LIP):
            cv2.circle(frame, (int(landmarks[idx].x * w), int(landmarks[idx].y * h)), 4, color, -1)
        p1 = (int(landmarks[_UPPER_LIP].x * w), int(landmarks[_UPPER_LIP].y * h))
        p2 = (int(landmarks[_LOWER_LIP].x * w), int(landmarks[_LOWER_LIP].y * h))
        cv2.line(frame, p1, p2, (255, 255, 255), 1)


# ==== ENTRY POINT ====


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LipActivityDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
