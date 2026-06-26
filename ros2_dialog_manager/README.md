# ros2_dialog_manager: task-driven spoken dialog orchestrator

The central node of the stack. It receives a high-level task, drives a turn-by-turn
spoken conversation through a finite-state machine (FSM) plus pluggable dialog
strategies, and delegates NLU/NLG to the LLM Manager and audio to speech_io. It is
robot-agnostic: it only consumes ASR, emotion and VAD topics and produces speech via
the `/speak` action.

See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Nodes

| Node (ros2 run name) | Description |
| --- | --- |
| `dialog_manager_node` | Single-dialog-at-a-time FSM orchestrator. Exposes the `DialogTask` action, manages LLM sessions, runs the active strategy, and handles barge-in. |

## Interfaces

| Name | Type | Direction |
| --- | --- | --- |
| `/dialog/execute_task` | `ros2_dialog_interfaces/action/DialogTask` | action server |
| `/transcription` | `std_msgs/String` | subscribe (ASR text) |
| `/user_emotion` | `std_msgs/String` (JSON, optional) | subscribe |
| `/user_speaking` | `std_msgs/Bool` (VAD barge-in) | subscribe |
| `/speak` | `ros2_dialog_interfaces/action/SpeakText` | action client (TTS) |
| `/llm/inference` | `ros2_llm_interfaces/action/LlmInference` | action client |
| `/llm/session/create` | `ros2_llm_interfaces/srv/CreateSession` | service client |
| `/llm/session/delete` | `ros2_llm_interfaces/srv/DeleteSession` | service client |

## Dialog modes

| Mode | What it does | Auto-detected? |
| --- | --- | --- |
| `slot_filling` | Collects structured slot values into a `DialogFrame`, then confirms. | Yes (default fallback) |
| `explanation` | Explains a topic and verifies the user understood it, re-phrasing if not. | Yes |
| `quiz` | Asks scored questions from `resources_json` and reports results. | No. Must be set explicitly in the goal (needs a question bank) |

The mode comes from the goal's `dialog_mode` field. When it is empty, the node asks the
LLM to classify between `slot_filling` and `explanation`.

## Usage

Bring up the whole stack (speech_io + LLM manager + dialog manager):

```bash
ros2 launch ros2_dialog_manager main.launch.py
```

Run the node alone (requires `app_params.yaml` and `prompts.yaml`):

```bash
ros2 run ros2_dialog_manager dialog_manager_node \
  --ros-args --params-file config/app_params.yaml --params-file config/prompts.yaml
```

Send a task (slot filling example):

```bash
ros2 action send_goal /dialog/execute_task ros2_dialog_interfaces/action/DialogTask \
  "{task_description: 'Take a coffee order', max_turns: 0}"
```

## Tests

Pure-Python unit tests, no ROS graph needed (173 tests):

```bash
python3 -m pytest test/ -q
```

## Configuration

Parameters live in [`config/app_params.yaml`](config/app_params.yaml) and prompt templates
in [`config/prompts.yaml`](config/prompts.yaml). See [../docs/configuration.md](../docs/configuration.md).
