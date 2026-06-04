"""
TestAudioNode — interactive terminal test for STT and TTS.

Subscribes to the speech-to-text output topic and prints every received
transcription. Also provides a small terminal interface to send text to the
text-to-speech action server.

Topics consumed:
  /transcription   (String) — text produced by SpeechToTextNode.

Action clients:
  /speak           (SpeakText) — text-to-speech playback handled by
                                 TextToSpeechNode.

Terminal commands:
  /help            Show available commands.
  /speed VALUE     Change TTS speed, for example: /speed 1.2
  /quit            Stop the test node.
  any other text   Send that text to the TTS action server.
"""

import threading

import rclpy

from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from std_msgs.msg import String

from ros2_dialog_interfaces.action import SpeakText

# ==== INTERACTIVE AUDIO TEST NODE ====


class TestAudioNode(Node):

    def __init__(self):
        super().__init__("test_audio_node")

        self._declare_parameters()
        self._read_parameters()

        self._cb = ReentrantCallbackGroup()
        self._running = threading.Event()
        self._running.set()

        self._speed = self.default_speed
        self._active_goal_handle = None
        self._active_goal_lock = threading.Lock()

        self._configure_ros_interfaces()

        self.get_logger().info("Test audio node ready.")
        self._print_help()

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("transcription_topic", "/transcription")
        self.declare_parameter("speak_action_name", "/speak")
        self.declare_parameter("default_speed", 1.0)

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self.transcription_topic = p("transcription_topic").value
        self.speak_action_name = p("speak_action_name").value
        self.default_speed = float(p("default_speed").value)

        if self.default_speed <= 0.0:
            self.default_speed = 1.0

    # ==== ROS INTERFACES ====

    def _configure_ros_interfaces(self) -> None:
        self.create_subscription(
            String,
            self.transcription_topic,
            self._on_transcription,
            10,
            callback_group=self._cb,
        )

        self._tts_client = ActionClient(
            self,
            SpeakText,
            self.speak_action_name,
            callback_group=self._cb,
        )

    # ==== TRANSCRIPTION SIDE ====

    def _on_transcription(self, msg: String) -> None:
        text = msg.data.strip()
        if not text:
            return

        print(f"\n[STT] {text}")
        print("> ", end="", flush=True)

    # ==== TERMINAL LOOP ====

    def run_terminal(self) -> None:
        """
        Blocking terminal loop. It runs in a separate thread while ROS spins in
        the main executor.
        """
        while rclpy.ok() and self._running.is_set():
            try:
                user_input = input("> ").strip()
            except EOFError:
                self.stop()
                break
            except KeyboardInterrupt:
                self.stop()
                break

            if not user_input:
                continue

            if user_input == "/quit":
                self.stop()
                break

            if user_input == "/help":
                self._print_help()
                continue

            if user_input.startswith("/speed"):
                self._handle_speed_command(user_input)
                continue

            if user_input == "/cancel":
                self._cancel_current_tts()
                continue

            self._send_tts(user_input)

    def _handle_speed_command(self, command: str) -> None:
        parts = command.split(maxsplit=1)

        if len(parts) != 2:
            print("[SYSTEM] Usage: /speed VALUE")
            return

        try:
            speed = float(parts[1])
        except ValueError:
            print("[SYSTEM] Invalid speed value.")
            return

        if speed <= 0.0:
            print("[SYSTEM] Speed must be greater than 0.")
            return

        self._speed = speed
        print(f"[SYSTEM] TTS speed set to {self._speed:.2f}")

    # ==== TTS ACTION CLIENT ====

    def _send_tts(self, text: str) -> None:
        if not self._tts_client.wait_for_server(timeout_sec=2.0):
            print("[SYSTEM] TTS action server is not available.")
            return

        goal = SpeakText.Goal()
        goal.text = text
        goal.speed = float(self._speed)

        print(f"[TTS] Sending: {text}")

        send_future = self._tts_client.send_goal_async(
            goal,
            feedback_callback=self._on_tts_feedback,
        )
        send_future.add_done_callback(self._on_tts_goal_response)

    def _on_tts_goal_response(self, future) -> None:
        goal_handle = future.result()

        if not goal_handle or not goal_handle.accepted:
            print("[TTS] Goal rejected.")
            print("> ", end="", flush=True)
            return

        with self._active_goal_lock:
            self._active_goal_handle = goal_handle

        print("[TTS] Goal accepted.")

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._on_tts_result)

    def _on_tts_feedback(self, feedback_msg) -> None:
        feedback = feedback_msg.feedback
        current_chunk = getattr(feedback, "current_chunk", "")
        if current_chunk:
            print(f"\r[TTS] Playing chunk {current_chunk}", end="", flush=True)

    def _on_tts_result(self, future) -> None:
        result = future.result().result

        with self._active_goal_lock:
            self._active_goal_handle = None

        print()
        print(
            f"[TTS] Finished: status={result.status}, "
            f"success={result.success}, duration={result.duration_s:.2f}s"
        )
        print("> ", end="", flush=True)

    def _cancel_current_tts(self) -> None:
        with self._active_goal_lock:
            goal_handle = self._active_goal_handle

        if goal_handle is None:
            print("[SYSTEM] No active TTS goal to cancel.")
            return

        goal_handle.cancel_goal_async()
        print("[SYSTEM] Cancel request sent.")

    # ==== LIFECYCLE HELPERS ====

    def stop(self) -> None:
        self._running.clear()
        print("[SYSTEM] Stopping test audio node.")
        if rclpy.ok():
            rclpy.shutdown()

    @staticmethod
    def _print_help() -> None:
        print()
        print("Interactive audio test")
        print("Available commands:")
        print("  /help         Show this help message")
        print("  /speed VALUE  Set TTS speed, for example: /speed 1.2")
        print("  /cancel       Cancel the current TTS playback")
        print("  /quit         Stop the node")
        print("  any text      Send text to the TTS action server")
        print()
        print("Incoming STT transcriptions will be printed automatically.")
        print()


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = TestAudioNode()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    terminal_thread = threading.Thread(
        target=node.run_terminal,
        daemon=True,
    )
    terminal_thread.start()

    try:
        executor.spin()
    except KeyboardInterrupt:
        node.stop()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
