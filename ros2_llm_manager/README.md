# ros2_llm_manager — multi-provider LLM inference for ROS 2

Wraps LLM inference behind a single ROS 2 action plus session-management services.
Supports local models via Ollama and cloud models via Google Gemini, with optional
stateful (history-keeping) sessions and JSON-schema-constrained output. The dialog
manager is its main client, but any node can use it.

See [../docs/architecture.md](../docs/architecture.md) for the full design.

## Nodes

| Node (ros2 run name) | Description |
| --- | --- |
| `llm_manager_node` | Inference action server with provider/session management (Ollama + Gemini). |
| `llm_cli_client` | Interactive terminal client to test connectivity, sessions and streaming. |

## Interfaces

| Name | Type | Direction |
| --- | --- | --- |
| `/llm/inference` | `ros2_llm_interfaces/action/LlmInference` | action server |
| `/llm/session/create` | `ros2_llm_interfaces/srv/CreateSession` | service server |
| `/llm/session/delete` | `ros2_llm_interfaces/srv/DeleteSession` | service server |
| `/llm/session/list` | `ros2_llm_interfaces/srv/ListSessions` | service server |

## Usage

```bash
ros2 launch ros2_llm_manager llm_manager.launch.py            # uses config/params.yaml
ros2 launch ros2_llm_manager llm_manager.launch.py params:=/path/to/params.yaml
```

Or run the node directly:

```bash
ros2 run ros2_llm_manager llm_manager_node --ros-args --params-file config/params.yaml
```

Interactive client (with the node running):

```bash
ros2 run ros2_llm_manager llm_cli_client
```

In the client, `/new [provider] [model]` opens a session, `/stateless` toggles history
for the next session, `/list` and `/info` inspect sessions, and any other text is sent
as a prompt to the active session. `/quit` closes all sessions and exits.

For Gemini, set the API key via the `GEMINI_API_KEY` environment variable (preferred)
or in the params file.

## Configuration

Provider selection, defaults and per-provider settings (Ollama host/model, Gemini model,
timeouts) live in [`config/params.yaml`](config/params.yaml). See
[../docs/configuration.md](../docs/configuration.md).
