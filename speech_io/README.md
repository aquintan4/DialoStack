# speech_io: speech input/output for ROS 2

Provides the spoken interface of the stack: speech-to-text (faster-whisper + Silero VAD)
and text-to-speech (Piper). It also publishes a voice-activity signal and a "robot is
speaking" flag so the dialog manager can mute the mic and support barge-in.

The sound can come from local hardware or travel over ROS as raw PCM (`AudioChunk`),
so the microphone and speaker can live on a robot, a Raspberry Pi or a browser tab while
the models run on another machine.

See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Nodes

| Node (ros2 run name) | Description |
| --- | --- |
| `speech_to_text_node` | Microphone ASR with VAD. Publishes final transcriptions and mutes itself while TTS plays. |
| `text_to_speech_node` | Synthesizes speech with Piper via the `SpeakText` action and signals playback state. |
| `audio_bridge_node` | Captures a local microphone to `/audio_in` and plays `/audio_out` on a local speaker. Run it on the robot while STT/TTS run elsewhere in topic mode. |
| `test_audio_node` | Interactive terminal tool to print transcriptions and send text to TTS. |

## Interfaces

| Name | Type | Direction |
| --- | --- | --- |
| `/transcription` | `std_msgs/String` | publish (STT) |
| `/user_vad` | `std_msgs/Float32` (VAD probability) | publish (STT) |
| `/is_speaking` | `std_msgs/Bool` | publish (TTS) / subscribe (STT) |
| `/speak` | `ros2_dialog_interfaces/action/SpeakText` | action server (TTS) |
| `/audio_in` | `ros2_dialog_interfaces/msg/AudioChunk` | subscribe (STT, `audio_source: topic`) / publish (bridge) |
| `/audio_out` | `ros2_dialog_interfaces/msg/AudioChunk` | publish (TTS, `audio_sink: topic`) / subscribe (bridge) |

## Usage

```bash
ros2 launch speech_io speech_io.launch.py                 # uses config/params.yaml
ros2 launch speech_io speech_io.launch.py params:=/path/to/params.yaml
```

Or run nodes individually:

```bash
ros2 run speech_io speech_to_text_node --ros-args --params-file config/params.yaml
ros2 run speech_io text_to_speech_node --ros-args --params-file config/params.yaml
ros2 run speech_io test_audio_node      # type text to speak, /quit to exit
```

### Remote audio (robot microphone and speaker)

On the robot, start the bridge:

```bash
ros2 launch speech_io audio_bridge.launch.py   # any Linux device with ALSA audio
ros2 launch speech_io nao_min.launch.py        # on a NAO: LoLA client + bridge
```

On the machine with the models, set `audio_source: topic` on the STT node and
`audio_sink: topic` on the TTS node (in the GUI: **Configuration > Audio > ROS topics**).
See [Audio routing](../docs/configuration.md#audio-routing).

### Piper voice required

The TTS node shells out to `piper` and loads the voice named by the `model_path`
parameter (default `en_US-lessac-medium.onnx`). A bare filename is resolved under
`DIALOSTACK_MODELS_DIR` (default `~/.local/share/dialostack/models`), so the config
carries only a filename. No model ships with this package. Run
`scripts/download_models.sh` to fetch the default voices, or download a Piper voice
yourself (the `.onnx` file and its `.onnx.json`) and set `model_path` to its filename
or an absolute path.

## Configuration

STT and TTS parameters (model size, language, device, VAD thresholds, Piper model path,
audio devices) live in [`config/params.yaml`](config/params.yaml). See
[../docs/configuration.md](../docs/configuration.md).
