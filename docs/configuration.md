# Configuration Reference

This document is the parameter reference for every ROS 2 node in the DialoStack
stack. See [architecture.md](architecture.md) for how these nodes interact.

## Conventions

The **Default** column shows the *shipped default*: the value the node actually
runs with after its YAML configuration is loaded. Where a YAML file overrides
the hard-coded `declare_parameter` default in the node, the YAML value is the
one listed, and any divergence between code and YAML is called out in the
[Code vs. YAML discrepancies](#code-vs-yaml-discrepancies) section at the end.

### Configuration files

| File | Purpose |
| --- | --- |
| `ros2_dialog_manager/config/app_params.yaml` | Shared parameters for the four nodes launched by `main.launch.py` (STT, TTS, LLM Manager, Dialog Manager). |
| `ros2_dialog_manager/config/prompts.yaml` | All LLM prompt templates for the Dialog Manager. |
| `ros2_llm_manager/config/params.yaml` | Standalone parameters for the LLM Manager node. |
| `speech_io/config/params.yaml` | Standalone parameters for the speech-to-text and text-to-speech nodes. |
| `vision_io/config/params.yaml` | Parameters for the emotion detector node. |
| `vision_io/config/lip_activity_params.yaml` | Parameters for the lip activity detector node. |
| `robots/nao/nao_pose_manager/config/nao_saved_poses.yaml` | Saved arm poses consumed by the gesture managers (not a parameter file). |

### Launch files

| Launch file | Loads | Nodes |
| --- | --- | --- |
| `ros2_dialog_manager/launch/main.launch.py` | `app_params.yaml` (all four nodes) plus `prompts.yaml` (Dialog Manager only) | `speech_to_text_node`, `text_to_speech_node`, `llm_manager_node`, `dialog_manager_node` |
| `ros2_llm_manager/launch/llm_manager.launch.py` | `params.yaml` | `llm_manager_node` |
| `speech_io/launch/speech_io.launch.py` | `params.yaml` | `speech_to_text_node`, `text_to_speech_node` |
| `vision_io/launch/emotion_detector.launch.py` | `params.yaml` | `emotion_detector` |
| `vision_io/launch/lip_detector.launch.py` | `lip_activity_params.yaml` | `lip_activity_detector_node` |
| `robots/nao/nao_pose_manager/launch/arm_gesture_manager.launch.py` | launch arguments (no YAML) | `arm_gesture_manager`, `eye_led_feedback` |

When the speech and LLM nodes are started through `main.launch.py` they take
their values from `app_params.yaml`. When started through their own packages'
launch files they take their values from the package's `params.yaml`. The two
files do not always agree, so check the discrepancies section.

## dialog_manager_node

Declared in `ros2_dialog_manager/ros2_dialog_manager/dialog_manager_node.py`;
shipped values from `ros2_dialog_manager/config/app_params.yaml`. The node is
created with `automatically_declare_parameters_from_overrides=True`, so the
`prompts.*` keys and any extra YAML keys are also declared automatically.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `transcription_topic` | string | `/transcription` | Topic carrying final user transcriptions from the STT node. |
| `user_emotion_topic` | string | `/user_emotion` | Topic carrying detected user emotion (JSON payload). |
| `user_speaking_topic` | string | `/user_speaking` | Topic carrying the user-speaking signal for barge-in. Set to `""` to disable barge-in. |
| `language` | string | `Spanish` | Language used for LLM generation and fallback phrases. Any language name is accepted. |
| `history_max_turns` | int | `200` | Maximum turns kept in the dialog history buffer. The oldest half is dropped when exceeded. |
| `ack_phrases` | string[] | `["Anotado.", "Hecho.", "Perfecto.", "Entendido.", "De acuerdo."]` | Acknowledgment phrases injected by the system after each successful slot extraction. Set to `[""]` to disable. |
| `wait_timeout` | float | `20.0` | Seconds to wait for a user reply before prompting again. |
| `llm_timeout` | float | `120.0` | Seconds to wait for an LLM Manager response. |
| `tts_timeout` | float | `60.0` | Seconds to wait for the TTS action to finish. |
| `timeout_prompt` | string | `¿Sigues ahí?` | Phrase spoken when the user does not respond within `wait_timeout`. |
| `max_timeouts` | int | `2` | Maximum consecutive timeouts before the FSM gives up. |
| `max_unclear` | int | `3` | Maximum consecutive unclear replies before the FSM gives up. |
| `max_attempts` | int | `3` | Maximum attempts per slot/explanation before escalating. |
| `llm_provider` | string | `""` | LLM Manager provider override. Empty means the node uses its own default. |
| `llm_model` | string | `""` | LLM Manager model override. Empty means the provider default. |
| `silent_mode` | bool | `false` | Disable informational logs when true. |
| `conversation_log_path` | string | `/tmp/dialog_conversations.log` | Transcript log path. Set to `""` to disable transcript logging. |
| `conversation_log_max_mb` | float | `10.0` | Rotate the transcript when it exceeds this size in MB. `0` = never rotate. |

The `prompts.*` parameters are documented separately under
[prompts.yaml](#promptsyaml).

## prompts.yaml

`ros2_dialog_manager/config/prompts.yaml` holds **all** LLM prompt templates
used by the Dialog Manager. They are loaded under the `prompts` parameter prefix
via `get_parameters_by_prefix("prompts")`, so templates can be edited and tuned
without changing any code.

Placeholders are filled with Python `str.format`: single braces such as
`{task}` or `{language}` are substituted, while any *literal* brace in a
template must be doubled (`{{` / `}}`). The `{language}` placeholder is injected
automatically by the `PromptBuilder` and is available to every template. The
node validates all templates at startup.

The templates, grouped by purpose:

- **Task setup / schema design:** `classify_task_mode`, `create_frame`,
  `audit_frame`
- **Slot-filling dialog:** `opening`, `resume_opening`, `extract_slots`,
  `generate_response`, `ask_confirmation`, `classify_intent`,
  `response_to_intent`, `answer_confirmation_question`
- **Quiz strategy:** `quiz_opening`, `evaluate_quiz_answer`,
  `quiz_next_question`, `quiz_summary`
- **Explanation strategy:** `explanation_opening`, `check_understanding`,
  `classify_understanding`, `answer_explanation_question`,
  `rephrase_explanation`, `understanding_confirmed`, `explanation_max_attempts`
- **Cancellation handling:** `detect_cancel_intent`,
  `detect_cancel_confirmation`, `ask_cancel_confirmation`,
  `cancel_confirmed_response`, `cancel_denied_response`

## llm_manager_node

Declared in `ros2_llm_manager/ros2_llm_manager/llm_manager_node.py`. Shipped
values from `ros2_llm_manager/config/params.yaml`. The Gemini provider reads its
API key from the `GEMINI_API_KEY` environment variable when `gemini.api_key` is
left empty (the recommended setup).

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `default_provider` | string | `gemini` | Provider used when a session request does not specify one. Must be an enabled provider (`gemini` or `ollama`). |
| `default_model` | string | `""` | Default model override. Empty means the provider's own default. |
| `max_concurrent` | int | `4` | Maximum number of concurrent inference threads. |
| `silent_mode` | bool | `false` | Disable informational logs when true. |
| `ollama.enable` | bool | `true` | Enable the Ollama provider and connect at startup. |
| `ollama.host` | string | `127.0.0.1` | Ollama server host. |
| `ollama.port` | int | `11434` | Ollama server port. |
| `ollama.model` | string | `llama3.2:3b` | Model to pre-load into VRAM on startup. |
| `ollama.timeout` | float | `120.0` | Request timeout in seconds for Ollama inference calls. |
| `gemini.enable` | bool | `true` | Enable the Gemini provider and connect at startup. |
| `gemini.api_key` | string | `""` | Google Gemini API key. Prefer the `GEMINI_API_KEY` environment variable and leave this empty. |
| `gemini.model` | string | `gemini-2.5-flash` | Gemini model name. |
| `gemini.timeout` | float | `60.0` | Request timeout in seconds for Gemini inference calls. |

## speech_to_text_node

Declared in `speech_io/speech_io/speech_to_text_node.py`. Shipped values from
`speech_io/config/params.yaml`. Uses `faster-whisper` for transcription and
Silero VAD for voice activity detection.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `output_topic` | string | `/transcription` | Topic where final transcriptions are published. |
| `is_speaking_topic` | string | `/is_speaking` | TTS playback signal. While true, STT mutes itself to avoid transcribing the robot. |
| `vad_topic` | string | `/user_vad` | Topic where the raw VAD probability is published as `Float32` in `[0, 1]`. |
| `input_device` | string | `''` | Microphone input device. Empty string uses the default system input. |
| `model_size` | string | `base` | faster-whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`, …). |
| `language` | string | `es` | Expected speech language (ISO code). |
| `device` | string | `cpu` | faster-whisper inference device (`cpu` or `cuda`). |
| `compute_type` | string | `int8` | faster-whisper compute type (e.g. `int8` for CPU, `float16`/`int8_float16` for CUDA). |
| `cpu_threads` | int | `4` | Number of CPU threads used by faster-whisper. |
| `sample_rate` | int | `16000` | Microphone sample rate expected by Silero VAD. |
| `vad_threshold` | float | `0.5` | Minimum Silero VAD probability to treat a chunk as speech. |
| `grace_period` | float | `0.8` | Seconds of silence allowed after speech before closing a phrase. |
| `max_phrase_secs` | float | `8.0` | Maximum phrase duration before forcing transcription. |
| `silent_mode` | bool | `false` | Disable informational logs when true. |

## text_to_speech_node

Declared in `speech_io/speech_io/text_to_speech_node.py`. Shipped values from
`speech_io/config/params.yaml`. Uses Piper for speech synthesis.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `action_name` | string | `/speak` | `SpeakText` action server name used to request synthesis. |
| `is_speaking_topic` | string | `/is_speaking` | Topic publishing whether TTS is currently playing. STT uses it to mute itself. |
| `model_path` | string | `models/es_ES-sharvard-medium.onnx` | Piper voice model used for synthesis. |
| `sample_rate` | int | `22050` | Output sample rate expected by the selected Piper model. |
| `audio_device` | string | `default` | Audio output device. `default` uses the system default output. |

## emotion_detector

Declared in `vision_io/vision_io/emotion_detector.py`. Shipped values from
`vision_io/config/params.yaml`.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `input_topic` | string | `/camera/image_raw` | Camera image topic consumed by the detector. |
| `output_topic` | string | `/user_emotion` | Topic publishing the detected emotion as JSON (`{"emotion", "confidence", "source"}`). |
| `model_name` | string | `dima806/face_emotions_image_detection` | Hugging Face model used for emotion classification. |
| `show_visualization` | bool | `true` | Show an OpenCV visualization window when true. |

## lip_activity_detector_node

Declared in `vision_io/vision_io/lip_activity_detector.py`. Shipped values from
`vision_io/config/lip_activity_params.yaml`. Detects user speech by combining
MediaPipe lip movement analysis with the audio VAD signal. The YAML node key
must exactly match the launch `name=` (`lip_activity_detector_node`).

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `image_topic` | string | `/camera/image_raw` | Camera image topic consumed by the detector. |
| `speaking_topic` | string | `/user_speaking` | Topic publishing the user-speaking `Bool` signal. |
| `lip_activity_topic` | string | `/lip_activity` | Topic publishing the raw lip-activity signal. |
| `min_detection_confidence` | float | `0.5` | MediaPipe face detection confidence threshold. |
| `min_tracking_confidence` | float | `0.5` | MediaPipe face tracking confidence threshold. |
| `open_threshold` | float | `0.04` | Margin above the resting-mouth baseline counted as "mouth open". |
| `smoothing_frames` | int | `4` | Light smoothing window that removes single-frame spikes. |
| `roughness_threshold` | float | `7.0e-6` | Variance-of-diffs threshold used to classify movement as speech. |
| `roughness_window` | int | `10` | Window (frames) over which roughness is computed (~0.33 s at 30 fps). |
| `onset_secs` | float | `0.90` | Minimum continuous high-roughness time required to enter the SPEAKING state. |
| `silence_secs` | float | `1.20` | Continuous closed-mouth time required before leaving the SPEAKING state. |
| `show_debug` | bool | `true` | Show an OpenCV debug window with landmarks, lip bars, and state. |

## gesture_manager

Declared in
`robots/nao/nao_pose_manager/nao_pose_manager/gesture_manager.py`. This node
publishes `JointState` for RViz/simulation visualisation. It has no dedicated
YAML file. The defaults below are the in-code `declare_parameter` defaults.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `poses_file` | string | `nao_saved_poses.yaml` | YAML file with the saved arm poses to load. |
| `transition_speed` | float | `0.03` | Interpolation speed between poses (rad/tick). |
| `idle_interval` | float | `3.0` | Seconds between idle pose changes. |
| `hold_time_min` | float | `1.0` | Minimum seconds to hold a gesture. |
| `hold_time_max` | float | `2.5` | Maximum seconds to hold a gesture. |

## arm_gesture_manager

Declared in
`robots/nao/nao_pose_manager/nao_pose_manager/arm_gesture_manager.py`. This node
drives the real NAO arms. Defaults below are the in-code `declare_parameter`
defaults. Values supplied through `arm_gesture_manager.launch.py` launch
arguments are noted where they differ.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `poses_file` | string | `""` | Path to the YAML file with saved poses. Launch default: the package's `config/nao_saved_poses.yaml`. |
| `transition_speed` | float | `0.03` | Interpolation speed between poses (rad/tick at 20 Hz). Launch default: `0.05`. |
| `idle_interval` | float | `3.0` | Seconds between idle pose changes. Launch default: `3.0`. |
| `hold_time_min` | float | `1.0` | Minimum seconds to hold a gesture. Launch default: `1.0`. |
| `hold_time_max` | float | `2.5` | Maximum seconds to hold a gesture. Launch default: `2.5`. |
| `stiffness` | float | `0.8` | Arm motor stiffness (`0.0`–`1.0`). Launch default: `0.8`. |

## eye_led_feedback

Declared in
`robots/nao/nao_pose_manager/nao_pose_manager/eye_led_feedback.py`. Drives the
NAO eye LEDs as interaction feedback. It is launched without a YAML file or
launch arguments, so the defaults below (in-code `declare_parameter` defaults)
always apply.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `vad_threshold` | float | `0.35` | Minimum VAD value to consider the user speaking (green eyes). |
| `pulse_hz` | float | `0.7` | Pulse frequency of the warm-white "robot speaking" state. |
| `pulse_amp` | float | `0.20` | Pulse brightness amplitude (± brightness). |
| `fade_speed` | float | `0.12` | Colour interpolation step per tick (10 Hz loop). |

## Code vs. YAML discrepancies

The following differences exist between the hard-coded `declare_parameter`
defaults and the shipped YAML values. They are reported here as-is and are not
modified by this document.

**Speech-to-text, `app_params.yaml` vs. code and `speech_io/params.yaml`:**
`app_params.yaml` ships `model_size: small`, `device: cuda`, and
`compute_type: float16`, whereas the node defaults (and `speech_io/params.yaml`)
use `base`, `cpu`, and `int8`. As a result the STT node runs with different
inference settings depending on which launch file starts it. Additionally,
`app_params.yaml` does not include `vad_topic`, so under `main.launch.py` the
node falls back to its code default `/user_vad`.

**LLM Manager, code vs. YAML:**
- `default_provider`: code default `""`. Both YAML files ship `gemini`.
- `ollama.enable`: code default `false`. `ros2_llm_manager/params.yaml` ships
  `true`, while `app_params.yaml` ships `false`.
- `gemini.enable`: code default `false`. Both YAML files ship `true`.
- `ollama.model`: code default `llama3.2:3b`. `app_params.yaml` ships
  `qwen2.5`, while `ros2_llm_manager/params.yaml` ships `llama3.2:3b`.
- `gemini.model`: code default `gemini-2.0-flash`. Both YAML files ship
  `gemini-2.5-flash`.

**Dialog Manager, code vs. `app_params.yaml`:**
- `timeout_prompt`: code default `""`. YAML ships `¿Sigues ahí?`.
- `ack_phrases`: code default `[""]` (disabled). YAML ships five phrases.

**Arm gesture manager, code vs. launch:**
`transition_speed` has an in-code default of `0.03` but the launch file passes
`0.05`. The `poses_file` in-code default is empty (`""`) while the launch file
supplies the package's `config/nao_saved_poses.yaml`.
