"""Unit tests for SpeechToTextNode._resolve_device (auto CPU/GPU selection)."""

from speech_io.speech_to_text_node import SpeechToTextNode

resolve = SpeechToTextNode._resolve_device


def test_auto_picks_gpu_when_available():
    assert resolve("auto", "auto", 1) == ("cuda", "int8_float32")


def test_auto_picks_cpu_without_gpu():
    assert resolve("auto", "auto", 0) == ("cpu", "int8")


def test_explicit_device_is_kept():
    assert resolve("cpu", "auto", 1) == ("cpu", "int8")
    assert resolve("cuda", "auto", 0) == ("cuda", "int8_float32")


def test_explicit_compute_type_is_kept():
    assert resolve("auto", "float16", 1) == ("cuda", "float16")
    assert resolve("cpu", "float32", 0) == ("cpu", "float32")
