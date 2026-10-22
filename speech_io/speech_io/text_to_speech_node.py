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
import queue
import subprocess
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd
import rclpy

from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy

from std_msgs.msg import Bool

from ros2_dialog_interfaces.action import SpeakText

# ==== SPEAKER PLAYER ====


class SpeakerPlayer:
    """
    Plays one utterance on a local output stream from a dedicated thread.

    Every call into the audio stack can block: when the sound server stalls
    (PulseAudio over WSLg, a hung PipeWire), even PortAudio's buffer queries
    wait on it. Keeping all of them on this thread lets the caller detect the
    stall and give up on the utterance instead of freezing the action server.
    A stalled thread is abandoned; it ends by itself if the server recovers.
    """

    def __init__(self, open_stream, stall_s: float, clock=time.monotonic):
        self._open_stream = open_stream
        self._stall_s = stall_s
        self._clock = clock
        self._queue = queue.Queue(maxsize=8)
        self._abort = threading.Event()
        self._done = threading.Event()
        self._last_progress = clock()
        self.error = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            stream = self._open_stream()
            stream.start()
            self._last_progress = self._clock()
            while not self._abort.is_set():
                chunk = self._queue.get()
                if chunk is None:
                    break
                stream.write(chunk)
                self._last_progress = self._clock()
            if self._abort.is_set():
                stream.abort()
            else:
                stream.stop()  # lets the buffered tail play out
            stream.close()
        except Exception as exc:  # reported through play()/finish()
            self.error = exc
        finally:
            self._done.set()

    def _stalled(self) -> bool:
        return self._clock() - self._last_progress > self._stall_s

    def _wait(self, step, should_stop) -> str:
        """Retry step() until it succeeds; return why it stopped otherwise."""
        while not step():
            if self.error is not None:
                return "error"
            if should_stop():
                self.abort()
                return "interrupted"
            if self._stalled():
                self.abort()
                return "stalled"
        return "completed"

    def play(self, chunk, should_stop) -> str:
        """Queue a chunk: "completed", "interrupted", "stalled" or "error"."""
        def put():
            try:
                self._queue.put(chunk, timeout=0.02)
                return True
            except queue.Full:
                return False
        return self._wait(put, should_stop)

    def finish(self, should_stop) -> str:
        """Wait until everything queued has been played."""
        status = self.play(None, should_stop)
        if status != "completed":
            return status
        status = self._wait(lambda: self._done.wait(0.02), should_stop)
        return "error" if status == "completed" and self.error is not None else status

    def abort(self) -> None:
        """Cut playback at once (the thread drops what is still queued)."""
        self._abort.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass


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
        self.declare_parameter("model_path", "en_US-lessac-medium.onnx")
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
        raw_model_path = p("model_path").value
        self.model_path = self._resolve_model_path(raw_model_path)
        if self.model_path != raw_model_path and os.path.isabs(raw_model_path):
            self.get_logger().warning(
                f"Voice not found at {raw_model_path}; using {self.model_path} instead."
            )
        if not os.path.isfile(self.model_path):
            self.get_logger().error(
                f"Piper voice not found: '{self.model_path}'. Run scripts/download_models.sh "
                "or fix model_path; every utterance will fail until then."
            )

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

        A bare filename (or relative path) is looked up under
        DIALOSTACK_MODELS_DIR, defaulting to ~/.local/share/dialostack/models
        (where scripts/download_models.sh places the voices). So the shipped
        config carries only a filename.

        Absolute paths are used as-is, unless the file does not exist and a
        voice with the same filename is in the models directory: a config
        written on another machine (or the host, when running in Docker) then
        still finds the voice.
        """
        if not model_path:
            return model_path
        models_dir = os.environ.get("DIALOSTACK_MODELS_DIR") or os.path.expanduser(
            "~/.local/share/dialostack/models"
        )
        if not os.path.isabs(model_path):
            return os.path.join(models_dir, model_path)
        fallback = os.path.join(models_dir, os.path.basename(model_path))
        if not os.path.isfile(model_path) and os.path.isfile(fallback):
            return fallback
        return model_path

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

        # Piper's stderr goes to a temp file (a pipe could fill up and block it)
        # so a failed synthesis can be reported instead of passing as silence.
        piper_err = tempfile.TemporaryFile()
        try:
            cmd = self._build_piper_command(speed)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=piper_err,
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

            if status == "completed" and played_chunks == 0:
                piper_err.seek(0)
                detail = piper_err.read().decode("utf-8", "replace").strip().splitlines()
                self.get_logger().error(
                    f"Piper produced no audio (model '{self.model_path}'): "
                    f"{detail[-1] if detail else 'no error output'}"
                )
                status = "error"

        except Exception as exc:
            self.get_logger().error(f"TTS Error: {exc}")
            status = "error"

        finally:
            piper_err.close()
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

    # Seconds the output device may stop taking audio before the utterance is
    # given up (a healthy device accepts a chunk every ~0.1 s).
    OUTPUT_STALL_S = 3.0

    def _stream_to_speaker(self, proc, goal_handle, stop_event):
        """Play Piper's raw PCM straight to the local audio device."""
        status = "completed"
        first_chunk_played = False
        played_chunks = 0
        chunk_size = 4096

        def should_stop():
            return stop_event.is_set() or goal_handle.is_cancel_requested

        # A generous buffer absorbs scheduling hiccups of bridged sound servers
        # (PulseAudio over WSLg, PipeWire) that would otherwise underrun and
        # garble the speech.
        player = SpeakerPlayer(
            lambda: sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                device=self._out_dev,
                latency="high",
            ),
            self.OUTPUT_STALL_S,
        )

        while True:
            if should_stop():
                player.abort()
                status = "interrupted"
                break

            raw_bytes = proc.stdout.read(chunk_size)
            if not raw_bytes:
                status = player.finish(should_stop)
                break

            audio_data = np.frombuffer(raw_bytes, dtype=np.int16)

            # Publish True only when real audio starts playing.
            if not first_chunk_played:
                self._publish_speaking(True)
                first_chunk_played = True

            status = player.play(audio_data, should_stop)
            if status != "completed":
                break

            played_chunks += 1
            self._publish_feedback(goal_handle, played_chunks)

        if status == "stalled":
            self.get_logger().error(
                f"Audio output stalled for {self.OUTPUT_STALL_S:.0f}s; utterance "
                "given up (check the sound server / audio device)."
            )
            status = "error"
        elif status == "error":
            self.get_logger().error(f"Audio output failed: {player.error}")
        return status, played_chunks

    # Seconds of audio a remote player may hold ahead of real time in topic
    # mode: enough to ride out network jitter, little enough to stop quickly.
    TOPIC_LEAD_S = 0.5

    def _stream_to_topic(self, proc, goal_handle, stop_event):
        """
        Publish Piper's raw PCM (S16LE mono @ sample_rate) as AudioChunk on a
        ROS topic so a remote player (audio_bridge_node, a robot driver, or any
        consumer of the contract) renders it on its speaker.

        Piper synthesizes much faster than real time, but chunks are published
        at playback pace, at most TOPIC_LEAD_S ahead: a whole utterance sent at
        once overflows the transport (rosbridge drops most of it on its way to a
        browser), and an interruption could not stop audio the player already
        has. /is_speaking is held True for the audio's real duration plus a
        latency pad, so STT stays muted and the dialog manager waits until
        playback truly ends.
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

            # Pace to playback: wait while the player already holds enough.
            while (total_samples / float(self.sample_rate)
                   - (time.monotonic() - play_start)) > self.TOPIC_LEAD_S:
                if stop_event.is_set() or goal_handle.is_cancel_requested:
                    break
                time.sleep(0.01)
            if stop_event.is_set() or goal_handle.is_cancel_requested:
                status = "interrupted"
                break

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
