"""
AudioBridgeNode — generic, platform-agnostic audio I/O bridge.

Captures the local microphone and/or plays incoming audio with sounddevice,
exchanging raw PCM over DialoStack's AudioChunk contract. Run this on any
device with an ALSA-accessible mic/speaker (a robot head, an SBC, a laptop) to
feed the speech nodes over ROS topics without any vendor audio stack — the
speech_to_text / text_to_speech nodes can then run elsewhere (e.g. a laptop
with the heavy models) while the sound is captured and played on the robot.

This is one of DialoStack's audio "flavours":
  - all-local   : run STT/TTS with audio_source=microphone / audio_sink=speaker.
  - this bridge : run STT/TTS in "topic" mode and this node on the robot.
  - own driver  : a robot publishes/consumes AudioChunk itself, no bridge needed.

Parameter 'mode':
  capture -> read mic, publish AudioChunk on capture_topic   (-> STT /audio_in)
  play    -> subscribe AudioChunk on play_topic, play speaker (<- TTS /audio_out)
  both    -> full-duplex on the same device (default)

Topics:
  publishes  capture_topic (AudioChunk) when mode in (capture, both)
  subscribes play_topic    (AudioChunk) when mode in (play, both)
"""

import threading

import numpy as np
import sounddevice as sd
import rclpy

from rclpy.node import Node
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy

from ros2_dialog_interfaces.msg import AudioChunk

# ==== AUDIO BRIDGE NODE ====


class AudioBridgeNode(Node):

    def __init__(self):
        super().__init__("audio_bridge_node")

        self._declare_parameters()
        self._read_parameters()

        self._configure_ros_interfaces()

        if self._mode in ("capture", "both"):
            self._start_capture()
        if self._mode in ("play", "both"):
            self._start_play()

        self.get_logger().info(f"Ready. (mode={self._mode})")

    # ==== PARAMETER HANDLING ====

    def _declare_parameters(self) -> None:
        # What this bridge does: capture, play or both (full-duplex).
        self.declare_parameter("mode", "both")

        # Topics carrying the AudioChunk contract.
        self.declare_parameter("capture_topic", "/audio_in")
        self.declare_parameter("play_topic", "/audio_out")

        # Mic capture rate; MUST match the STT node's 'sample_rate' (16000).
        self.declare_parameter("capture_sample_rate", 16000)

        # ALSA device selection. Empty string uses the system default.
        self.declare_parameter("input_device", "")
        self.declare_parameter("output_device", "")

        # Mic chunk size in samples; 512 mirrors the STT VAD frame.
        self.declare_parameter("blocksize", 512)

    def _read_parameters(self) -> None:
        p = self.get_parameter

        self._mode = p("mode").value
        self._capture_topic = p("capture_topic").value
        self._play_topic = p("play_topic").value
        self._capture_rate = int(p("capture_sample_rate").value)
        self._blocksize = int(p("blocksize").value)

        in_dev = p("input_device").value
        out_dev = p("output_device").value
        self._in_dev = in_dev if in_dev else None
        self._out_dev = out_dev if out_dev else None

    # ==== ROS INTERFACES ====

    def _configure_ros_interfaces(self) -> None:
        # Capture is published BEST_EFFORT to match the STT input subscription:
        # for a live stream a dropped frame is better than head-of-line blocking.
        self._capture_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        # Playback is RELIABLE to match the TTS output publisher, so no synthesized
        # chunk is silently dropped on the way to the speaker.
        self._play_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=64,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

    # ==== CAPTURE (mic -> AudioChunk) ====

    def _start_capture(self) -> None:
        self._capture_pub = self.create_publisher(
            AudioChunk, self._capture_topic, self._capture_qos,
        )
        threading.Thread(target=self._capture_loop, daemon=True).start()
        self.get_logger().info(
            f"Capturing mic -> '{self._capture_topic}' @ {self._capture_rate} Hz"
        )

    def _capture_loop(self) -> None:
        def callback(indata, frames, time_info, status):
            # indata is int16 mono; publish the raw little-endian bytes as-is.
            msg = AudioChunk()
            msg.data = indata.tobytes()
            msg.sample_rate = self._capture_rate
            msg.channels = 1
            msg.encoding = "S16LE"
            self._capture_pub.publish(msg)

        while rclpy.ok():
            try:
                with sd.InputStream(
                    samplerate=self._capture_rate,
                    channels=1,
                    dtype="int16",
                    device=self._in_dev,
                    callback=callback,
                    blocksize=self._blocksize,
                ):
                    while rclpy.ok():
                        sd.sleep(100)
            except Exception as exc:
                self.get_logger().error(f"Capture hardware error: {exc}. Retrying...")
                sd.sleep(2000)

    # ==== PLAYBACK (AudioChunk -> speaker) ====
    #
    # The subscription must NEVER block: it only appends the incoming PCM to a
    # ring buffer and returns immediately, so the DDS queue is drained instantly
    # and no audio is dropped (a blocking write here, with Piper sending a whole
    # phrase faster than real time, stalls the executor and the middleware
    # discards chunks -> chopped, unintelligible speech).
    #
    # A sounddevice callback pulls samples from the buffer at a steady rate, with
    # a small jitter buffer to absorb network delay. On underrun it emits silence
    # (a brief gap) instead of garbage.

    def _start_play(self) -> None:
        self._play_stream = None
        self._play_rate = None
        self._play_lock = threading.Lock()      # guards (re)opening the stream
        self._pcm_buf = bytearray()             # pending S16LE bytes to play
        self._buf_lock = threading.Lock()       # guards _pcm_buf and _priming
        self._priming = True                    # build the jitter buffer first
        self._prime_bytes = 0                   # set when the stream opens

        self.create_subscription(
            AudioChunk, self._play_topic, self._on_play_msg, self._play_qos,
        )
        self.get_logger().info(f"Playing '{self._play_topic}' -> speaker")

    def _on_play_msg(self, msg) -> None:
        if not msg.data:
            return

        rate = int(msg.sample_rate) if msg.sample_rate else 22050

        with self._play_lock:
            # (Re)open the output stream lazily and whenever the incoming rate
            # changes, so the bridge follows whatever the producer sends.
            if self._play_stream is None or rate != self._play_rate:
                self._open_play_stream(rate)

        # Just buffer it; the callback below does the actual playback.
        with self._buf_lock:
            self._pcm_buf.extend(bytes(msg.data))

    def _play_callback(self, outdata, frames, time_info, status) -> None:
        needed = frames * 2  # 2 bytes per int16 mono frame

        with self._buf_lock:
            if self._priming:
                # Hold (silence) until a small jitter buffer has accumulated.
                if len(self._pcm_buf) < self._prime_bytes:
                    outdata[:] = 0
                    return
                self._priming = False

            n = min(needed, len(self._pcm_buf))
            chunk = bytes(self._pcm_buf[:n])
            del self._pcm_buf[:n]
            if n == 0:
                # Fully drained: re-prime so the next phrase rebuilds its buffer
                # before playing, instead of stuttering on the first samples.
                self._priming = True

        if n < needed:
            chunk += b"\x00" * (needed - n)  # zero-fill underrun (gap, not noise)
        outdata[:] = np.frombuffer(chunk, dtype=np.int16).reshape(-1, 1)

    def _open_play_stream(self, rate: int) -> None:
        if self._play_stream is not None:
            try:
                self._play_stream.stop()
                self._play_stream.close()
            except Exception:
                pass

        with self._buf_lock:
            self._pcm_buf = bytearray()
            self._priming = True
            self._prime_bytes = int(rate * 2 * 0.15)  # ~150 ms of S16LE mono

        self._play_stream = sd.OutputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            device=self._out_dev,
            callback=self._play_callback,
        )
        self._play_stream.start()
        self._play_rate = rate
        self.get_logger().info(
            f"Output stream opened @ {rate} Hz (callback, ~150 ms jitter buffer)"
        )


# ==== ENTRY POINT ====


def main(args=None):
    rclpy.init(args=args)
    node = AudioBridgeNode()

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
