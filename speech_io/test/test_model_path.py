"""Unit tests for TextToSpeechNode._resolve_model_path (Piper voice lookup)."""

from speech_io.text_to_speech_node import TextToSpeechNode

resolve = TextToSpeechNode._resolve_model_path


def test_filename_resolves_under_models_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DIALOSTACK_MODELS_DIR", str(tmp_path))
    assert resolve("voice.onnx") == str(tmp_path / "voice.onnx")


def test_existing_absolute_path_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("DIALOSTACK_MODELS_DIR", str(tmp_path / "models"))
    voice = tmp_path / "voice.onnx"
    voice.write_bytes(b"")
    assert resolve(str(voice)) == str(voice)


def test_missing_absolute_path_falls_back_to_models_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DIALOSTACK_MODELS_DIR", str(tmp_path))
    (tmp_path / "voice.onnx").write_bytes(b"")
    assert resolve("/home/someone/models/voice.onnx") == str(tmp_path / "voice.onnx")


def test_missing_absolute_path_without_fallback_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("DIALOSTACK_MODELS_DIR", str(tmp_path))
    assert resolve("/nowhere/voice.onnx") == "/nowhere/voice.onnx"


def test_empty_path_is_kept():
    assert resolve("") == ""
