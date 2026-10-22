"""Unit tests for SpeakerPlayer (local playback that survives a stalled device)."""

import threading
import time

import numpy as np

from speech_io.text_to_speech_node import SpeakerPlayer

CHUNK = np.zeros(4, dtype=np.int16)


class FakeStream:
    """Output stream whose write() blocks while `gate` is cleared."""

    def __init__(self):
        self.gate = threading.Event()
        self.gate.set()
        self.written = 0
        self.ended = None

    def start(self):
        pass

    def write(self, data):
        self.gate.wait()
        self.written += len(data)

    def stop(self):
        self.ended = "stop"

    def abort(self):
        self.ended = "abort"

    def close(self):
        pass


def never():
    return False


def test_plays_everything_and_drains():
    stream = FakeStream()
    player = SpeakerPlayer(lambda: stream, stall_s=1.0)
    for _ in range(20):
        assert player.play(CHUNK, never) == "completed"
    assert player.finish(never) == "completed"
    assert stream.written == 20 * len(CHUNK)
    assert stream.ended == "stop"


def test_blocked_device_is_given_up_instead_of_hanging():
    stream = FakeStream()
    stream.gate.clear()  # the sound server stops answering
    player = SpeakerPlayer(lambda: stream, stall_s=0.3)
    t0 = time.monotonic()
    statuses = [player.play(CHUNK, never) for _ in range(20)]
    assert "stalled" in statuses
    assert time.monotonic() - t0 < 2.0
    stream.gate.set()  # let the abandoned thread finish


def test_interruption_cuts_playback():
    stream = FakeStream()
    stream.gate.clear()
    player = SpeakerPlayer(lambda: stream, stall_s=5.0)
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    statuses = [player.play(CHUNK, stop.is_set) for _ in range(20)]
    assert statuses[-1] == "interrupted"
    stream.gate.set()
    time.sleep(0.1)
    assert stream.ended == "abort"


def test_device_error_is_reported():
    def broken():
        raise RuntimeError("no such device")

    player = SpeakerPlayer(broken, stall_s=1.0)
    time.sleep(0.05)
    assert player.finish(never) == "error"
    assert "no such device" in str(player.error)
