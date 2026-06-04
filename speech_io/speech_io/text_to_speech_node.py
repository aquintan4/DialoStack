"""
TextToSpeechNode — ROS2 action server for streaming text-to-speech playback.

Receives text through the SpeakText action, synthesizes speech with Piper, and
streams the generated raw audio directly to the selected output device.

Topics published:
  /is_speaking   (Bool) — True while audio is being played, False otherwise.
                          Latched so late subscribers know the current state.

Action server:
  /speak         (SpeakText) — synthesizes and plays the requested text.

The node supports interruption: a new goal or a cancel request stops the
currently running playback before accepting or finishing the next operation.
"""

import threading
import time
import subprocess

import numpy as np
import sounddevice as sd
import rclpy

from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy

from std_msgs.msg import Bool

from ros2_dialog_interfaces.action import SpeakText

# ==== TEXT-TO-SPEECH NODE ====


class TextToSpeechNode(Node):

    def __init__(self):
        super().__init__("text_to_speech_node")

        self._declare_parameters()
        self._read_parameters()

        self._stop = threading.Event()
        self._stop_lock = threading.Lock()

        self._configure_ros_interfaces()

        self.get_logger().info("Ready.")

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("action_name", "/speak")
        self.declare_parameter("is_speaking_topic", "/is_speaking")
        self.declare_parameter("model_path", "models/es_ES-sharvard-medium.onnx")
        self.declare_parameter("sample_rate", 22050)
        self.declare_parameter("audio_device", "default")

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self.sample_rate = p("sample_rate").value
        self.model_path = p("model_path").value

        audio_device = p("audio_device").value
        self._out_dev = None if audio_device == "default" else audio_device

    # ==== ROS INTERFACES ====

    def _configure_ros_interfaces(self) -> None:
        p = self.get_parameter

        latched_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self._speaking_pub = self.create_publisher(
            Bool,
            p("is_speaking_topic").value,
            latched_qos,
        )
        self._publish_speaking(False)

        ActionServer(
            self,
            SpeakText,
            p("action_name").value,
            execute_callback=self._execute,
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
        )

    # ==== ACTION CALLBACKS ====

    def _on_goal(self, goal_request) -> GoalResponse:
        """
        Accept every new goal and request the current playback to stop first.
        The active execute loop observes this event and exits cleanly.
        """
        self.get_logger().info(f"Goal: '{goal_request.text[:60]}'")
        self._request_stop()
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle) -> CancelResponse:
        """Cancel requests are translated into the same stop signal."""
        self._request_stop()
        return CancelResponse.ACCEPT

    def _execute(self, goal_handle) -> SpeakText.Result:
        text = goal_handle.request.text.strip()
        speed = float(goal_handle.request.speed)

        if speed <= 0.0:
            speed = 1.0

        if not text:
            goal_handle.abort()
            return SpeakText.Result(success=False, status="error", duration_s=0.0)

        stop_event = self._replace_stop_event()

        start_time = time.monotonic()
        played_chunks = 0
        status = "completed"
        first_chunk_played = False

        try:
            cmd = self._build_piper_command(speed)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

            try:
                proc.stdin.write((text + "\n").encode("utf-8"))
                proc.stdin.close()

                with sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    device=self._out_dev,
                ) as stream:

                    chunk_size = 4096

                    while True:
                        if stop_event.is_set() or goal_handle.is_cancel_requested:
                            status = "interrupted"
                            break

                        raw_bytes = proc.stdout.read(chunk_size)
                        if not raw_bytes:
                            break

                        audio_data = np.frombuffer(raw_bytes, dtype=np.int16)

                        # Publish True only when real audio starts playing.
                        if not first_chunk_played:
                            self._publish_speaking(True)
                            first_chunk_played = True

                        stream.write(audio_data)

                        played_chunks += 1
                        self._publish_feedback(goal_handle, played_chunks)

            finally:
                proc.terminate()
                proc.wait()

        except Exception as exc:
            self.get_logger().error(f"TTS Error: {exc}")
            status = "error"

        finally:
            self._publish_speaking(False)

        duration = time.monotonic() - start_time
        result = SpeakText.Result(
            success=status == "completed",
            status=status,
            duration_s=duration,
        )

        self._finish_goal(goal_handle, status)

        self.get_logger().info(f"TTS {status} - {duration:.1f}s ({played_chunks} chunks)")
        return result

    # ==== PLAYBACK HELPERS ====

    def _build_piper_command(self, speed: float) -> list[str]:
        return [
            "piper",
            "--model",
            self.model_path,
            "--output-raw",
            "--length_scale",
            str(1.0 / speed),
        ]

    def _request_stop(self) -> None:
        with self._stop_lock:
            self._stop.set()

    def _replace_stop_event(self) -> threading.Event:
        """
        Each accepted goal owns its own stop event. New goals/cancels signal the
        currently active one through _request_stop().
        """
        stop_event = threading.Event()
        with self._stop_lock:
            self._stop = stop_event
        return stop_event

    # ==== ROS PUBLISHING HELPERS ====

    def _publish_speaking(self, speaking: bool) -> None:
        self._speaking_pub.publish(Bool(data=speaking))

    @staticmethod
    def _publish_feedback(goal_handle, played_chunks: int) -> None:
        goal_handle.publish_feedback(
            SpeakText.Feedback(
                progress=0.0,
                current_chunk=str(played_chunks),
                is_speaking=True,
            )
        )

    @staticmethod
    def _finish_goal(goal_handle, status: str) -> None:
        if status == "interrupted" and goal_handle.is_cancel_requested:
            goal_handle.canceled()
        elif status in ("interrupted", "error"):
            goal_handle.abort()
        else:
            goal_handle.succeed()


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = TextToSpeechNode()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
