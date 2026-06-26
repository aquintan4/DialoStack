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

import os
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
        self.declare_parameter("model_path", "es_ES-sharvard-medium.onnx")
        self.declare_parameter("sample_rate", 22050)
        self.declare_parameter("audio_device", "default")
        # Audio output sink: "speaker" (local, default) or "topic" (raw S16LE
        # PCM published as AudioChunk for a remote player — the built-in
        # audio_bridge_node, a robot's own driver, or any consumer of the
        # contract). The latency pad is extra seconds /is_speaking stays True
        # after publishing, to cover network/playback delay on that speaker.
        self.declare_parameter("audio_sink", "speaker")
        self.declare_parameter("audio_topic", "/audio_out")
        self.declare_parameter("topic_latency_pad", 0.3)

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self.sample_rate = p("sample_rate").value
        self.model_path = self._resolve_model_path(p("model_path").value)

        self._audio_sink = p("audio_sink").value
        self._audio_topic = p("audio_topic").value
        self._topic_latency_pad = p("topic_latency_pad").value

        # Only the speaker path touches the local audio hardware.
        if self._audio_sink == "speaker":
            audio_device = p("audio_device").value
            self._out_dev = None if audio_device == "default" else audio_device
        else:
            self._out_dev = None

    @staticmethod
    def _resolve_model_path(model_path: str) -> str:
        """Resolve a Piper voice path so configs stay machine-independent.

        Absolute paths are used as-is. A bare filename (or relative path) is
        looked up under DIALOSTACK_MODELS_DIR, defaulting to
        ~/.local/share/dialostack/models (where scripts/download_models.sh
        places the voices). So the shipped config carries only a filename.
        """
        if not model_path or os.path.isabs(model_path):
            return model_path
        models_dir = os.environ.get("DIALOSTACK_MODELS_DIR") or os.path.expanduser(
            "~/.local/share/dialostack/models"
        )
        return os.path.join(models_dir, model_path)

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

        # In topic mode, publish synthesized PCM for a remote audio_play_node.
        # RELIABLE QoS to match audio_play's default subscription.
        self._audio_pub = None
        if self._audio_sink == "topic":
            from ros2_dialog_interfaces.msg import AudioChunk  # lazy: topic mode only
            self._AudioChunk = AudioChunk
            audio_out_qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE,
            )
            self._audio_pub = self.create_publisher(
                AudioChunk, self._audio_topic, audio_out_qos,
            )
            self.get_logger().info(
                f"Publishing TTS audio on topic '{self._audio_topic}'"
            )

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

                if self._audio_sink == "topic":
                    status, played_chunks = self._stream_to_topic(
                        proc, goal_handle, stop_event,
                    )
                else:
                    status, played_chunks = self._stream_to_speaker(
                        proc, goal_handle, stop_event,
                    )

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

    def _stream_to_speaker(self, proc, goal_handle, stop_event):
        """Play Piper's raw PCM straight to the local audio device."""
        status = "completed"
        first_chunk_played = False
        played_chunks = 0
        chunk_size = 4096

        with sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self._out_dev,
        ) as stream:

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

        return status, played_chunks

    def _stream_to_topic(self, proc, goal_handle, stop_event):
        """
        Publish Piper's raw PCM (S16LE mono @ sample_rate) as AudioChunk on a
        ROS topic so a remote player (audio_bridge_node, a robot driver, or any
        consumer of the contract) renders it on its speaker.

        Piper synthesizes faster than real time, so chunks are published as soon
        as they are produced and then /is_speaking is held True for the audio's
        real duration plus a latency pad. This keeps turn-taking correct: STT
        stays muted and the dialog manager waits until playback truly ends.

        Limitation: the remote player buffers what it receives, so a mid-
        utterance interruption stops further publishing but audio already sent
        finishes playing on the robot.
        """
        status = "completed"
        first_chunk_played = False
        played_chunks = 0
        total_samples = 0
        chunk_size = 4096
        play_start = None

        while True:
            if stop_event.is_set() or goal_handle.is_cancel_requested:
                status = "interrupted"
                break

            raw_bytes = proc.stdout.read(chunk_size)
            if not raw_bytes:
                break

            if not first_chunk_played:
                self._publish_speaking(True)
                first_chunk_played = True
                play_start = time.monotonic()

            msg = self._AudioChunk()
            msg.data = raw_bytes                 # uint8[] accepts a bytes object
            msg.sample_rate = int(self.sample_rate)
            msg.channels = 1
            msg.encoding = "S16LE"
            self._audio_pub.publish(msg)

            total_samples += len(raw_bytes) // 2  # int16 -> 2 bytes/sample
            played_chunks += 1
            self._publish_feedback(goal_handle, played_chunks)

        # Hold /is_speaking until the remote speaker has actually finished.
        if first_chunk_played and total_samples > 0 and status != "interrupted":
            play_secs = total_samples / float(self.sample_rate)
            deadline = play_start + play_secs + self._topic_latency_pad
            while time.monotonic() < deadline:
                if stop_event.is_set() or goal_handle.is_cancel_requested:
                    status = "interrupted"
                    break
                time.sleep(0.05)

        return status, played_chunks

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
