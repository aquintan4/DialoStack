"""
SpeechToTextNode — ROS2 node for microphone-based speech transcription.

Captures microphone audio, runs Silero VAD to detect speech segments, and
transcribes completed phrases with faster-whisper.

Topics published:
  /transcription   (String)  — final ASR text.
  /user_vad        (Float32) — raw VAD probability in [0, 1].

Topics consumed:
  /is_speaking     (Bool)    — True while TTS is speaking. Used to mute input
                               and clear pending audio to avoid self-listening.

The node is intentionally split into three background loops:
  - capture loop:    reads audio chunks from the microphone.
  - VAD loop:        groups chunks into speech phrases.
  - inference loop:  transcribes completed phrases.
"""

import threading
import queue

import numpy as np
import sounddevice as sd
import rclpy
import torch

from rclpy.node import Node
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy

from std_msgs.msg import String, Bool, Float32
from faster_whisper import WhisperModel

# ==== SPEECH-TO-TEXT NODE ====


class SpeechToTextNode(Node):

    def __init__(self):
        super().__init__("speech_to_text_node")

        self._declare_parameters()
        self._read_parameters()

        self._muted = False
        self._reset_vad = False
        self._mute_lock = threading.Lock()

        self._raw_q = queue.Queue(maxsize=50)
        self._phrase_q = queue.Queue(maxsize=5)

        self._load_vad_model()
        self._load_asr_model()
        self._configure_ros_interfaces()

        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._vad_loop, daemon=True).start()
        threading.Thread(target=self._inference_loop, daemon=True).start()

        self._log("Ready.")

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        self.declare_parameter("output_topic", "/transcription")
        self.declare_parameter("is_speaking_topic", "/is_speaking")
        self.declare_parameter("vad_topic", "/user_vad")
        self.declare_parameter("input_device", "")
        self.declare_parameter("model_size", "base")
        self.declare_parameter("sample_rate", 16000)
        self.declare_parameter("language", "es")
        self.declare_parameter("vad_threshold", 0.5)
        self.declare_parameter("grace_period", 0.8)
        self.declare_parameter("max_phrase_secs", 8.0)
        self.declare_parameter("device", "cpu")
        self.declare_parameter("compute_type", "int8")
        self.declare_parameter("cpu_threads", 4)
        self.declare_parameter("silent_mode", False)

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self.sample_rate = p("sample_rate").value
        self.language = p("language").value
        self.vad_threshold = p("vad_threshold").value
        self.grace_period = p("grace_period").value
        self.max_phrase_secs = p("max_phrase_secs").value
        self.silent_mode = p("silent_mode").value

        input_dev = p("input_device").value
        self._input_dev = input_dev if input_dev else sd.default.device[0]

    # ==== MODEL LOADING ====

    def _load_vad_model(self) -> None:
        self._log("Loading Silero VAD...")

        self._vad_model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )

    def _load_asr_model(self) -> None:
        p = self.get_parameter
        self._log(f"Loading Whisper ({p('model_size').value})...")

        self._asr = WhisperModel(
            p("model_size").value,
            device=p("device").value,
            compute_type=p("compute_type").value,
            cpu_threads=p("cpu_threads").value,
        )

    # ==== ROS INTERFACES ====

    def _configure_ros_interfaces(self) -> None:
        p = self.get_parameter

        transcription_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        volatile_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._transcription_pub = self.create_publisher(
            String,
            p("output_topic").value,
            transcription_qos,
        )

        self._vad_pub = self.create_publisher(
            Float32,
            p("vad_topic").value,
            volatile_qos,
        )

        self.create_subscription(
            Bool,
            p("is_speaking_topic").value,
            self._on_tts_speaking,
            volatile_qos,
        )

    # ==== TTS MUTE HANDLING ====

    def _on_tts_speaking(self, msg: Bool) -> None:
        """
        Mute microphone processing while TTS is active and discard pending audio.
        This prevents the node from transcribing the robot's own voice.
        """
        with self._mute_lock:
            self._muted = msg.data
            if msg.data:
                self._reset_vad = True

        if msg.data:
            self._clear_queue(self._raw_q, mark_done=False)
            self._clear_queue(self._phrase_q, mark_done=True)

        state = "Muted" if msg.data else "Unmuted"
        reason = "speaking" if msg.data else "done"
        self._log(f"{state} - TTS {reason}")

    @staticmethod
    def _clear_queue(q: queue.Queue, mark_done: bool) -> None:
        while not q.empty():
            try:
                q.get_nowait()
                if mark_done:
                    q.task_done()
            except queue.Empty:
                break

    # ==== AUDIO CAPTURE ====

    def _capture_loop(self) -> None:
        def callback(indata, frames, time_info, status):
            with self._mute_lock:
                muted = self._muted

            if not muted:
                try:
                    self._raw_q.put_nowait(indata.copy())
                except queue.Full:
                    pass

        while rclpy.ok():
            try:
                with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    device=self._input_dev,
                    callback=callback,
                    blocksize=512,
                ):
                    while rclpy.ok():
                        sd.sleep(100)

            except Exception as exc:
                self._log_error(f"Audio hardware error: {exc}. Retrying...")
                sd.sleep(2000)

    # ==== VOICE ACTIVITY DETECTION ====

    def _vad_loop(self) -> None:
        chunk_size = 512
        max_silence = int(self.grace_period * self.sample_rate / chunk_size)
        max_chunks = int(self.max_phrase_secs * self.sample_rate / chunk_size)
        min_chunks = 5

        phrase = []
        silence = 0

        while rclpy.ok():
            with self._mute_lock:
                reset_vad = self._reset_vad
                if self._reset_vad:
                    self._reset_vad = False

            if reset_vad:
                phrase = []
                silence = 0

            try:
                chunk = self._raw_q.get(timeout=0.5)

                tensor_chunk = torch.from_numpy(chunk.flatten()).float()
                speech_prob = self._vad_model(tensor_chunk, self.sample_rate).item()
                is_voice = speech_prob > self.vad_threshold

                self._vad_pub.publish(Float32(data=float(speech_prob)))

                if is_voice:
                    phrase.append(chunk)
                    silence = 0
                elif phrase:
                    phrase.append(chunk)
                    silence += 1

                if silence > max_silence and phrase:
                    self._flush_phrase(phrase, min_chunks)
                    phrase, silence = [], 0

                if len(phrase) > max_chunks:
                    self._flush_phrase(phrase, min_chunks)
                    phrase, silence = [], 0

            except queue.Empty:
                continue

    def _flush_phrase(self, chunks: list[np.ndarray], min_chunks: int) -> None:
        """Send a completed phrase to the inference queue."""
        if len(chunks) <= min_chunks:
            return

        audio = np.concatenate(chunks).flatten()

        try:
            self._phrase_q.put_nowait(audio)
        except queue.Full:
            self._log_warn("Phrase discarded - queue full")

    # ==== SPEECH RECOGNITION ====

    def _inference_loop(self) -> None:
        while rclpy.ok():
            try:
                audio = self._phrase_q.get(timeout=0.5)

                segments, _ = self._asr.transcribe(
                    audio,
                    language=self.language,
                    beam_size=3,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                )

                text = "".join(segment.text for segment in segments).strip()

                if text:
                    self._log(f"Transcription: {text}")
                    self._publish_transcription(text)

                self._phrase_q.task_done()

            except queue.Empty:
                continue

            except Exception as exc:
                self.get_logger().error(f"Inference: {exc}")
                self._phrase_q.task_done()

    def _publish_transcription(self, text: str) -> None:
        msg = String()
        msg.data = text
        self._transcription_pub.publish(msg)

    # ==== LOGGING HELPERS ====

    def _log(self, msg: str) -> None:
        if not self.silent_mode:
            self.get_logger().info(msg)

    def _log_warn(self, msg: str) -> None:
        if not self.silent_mode:
            self.get_logger().warn(msg)

    def _log_error(self, msg: str) -> None:
        if not self.silent_mode:
            self.get_logger().error(msg)


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = SpeechToTextNode()

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
