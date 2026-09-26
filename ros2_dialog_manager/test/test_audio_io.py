"""Unit tests for RosAudioIO cancellation: a cancelled dialog must stop
listening and speaking immediately instead of waiting out the timeout."""

import threading
import time

from ros2_dialog_manager.audio_io import RosAudioIO


class _FakeNode:
    """Records _speak_sync calls; stands in for DialogManagerNode."""

    def __init__(self):
        self.spoken = []

    def _speak_sync(self, text, interrupt_event, cancel_event=None):
        self.spoken.append(text)


# ==== LISTEN ====


def test_listen_returns_transcription():
    audio = RosAudioIO(_FakeNode(), timeout=2.0)
    threading.Timer(0.05, audio.on_transcription, args=("hola",)).start()
    assert audio.listen() == "hola"


def test_cancel_wakes_blocked_listen():
    audio = RosAudioIO(_FakeNode(), timeout=20.0)
    threading.Timer(0.05, audio.cancel).start()
    t0 = time.monotonic()
    assert audio.listen() is None
    assert time.monotonic() - t0 < 1.0
    assert audio.cancelled


def test_listen_after_cancel_returns_immediately():
    audio = RosAudioIO(_FakeNode(), timeout=20.0)
    audio.cancel()
    t0 = time.monotonic()
    assert audio.listen() is None
    assert time.monotonic() - t0 < 0.1


# ==== SPEAK ====


def test_speak_after_cancel_is_silent():
    node = _FakeNode()
    audio = RosAudioIO(node, timeout=1.0)
    audio.speak("uno")
    audio.cancel()
    audio.speak("dos")
    assert node.spoken == ["uno"]
