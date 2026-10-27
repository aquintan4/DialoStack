# Installation

There are two ways to run DialoStack:

| | Docker image | Source build |
|---|---|---|
| Setup time | One command | ROS 2 Jazzy or Lyrical workspace + `colcon build` |
| Includes | Dialogue core, speech models, web GUI | Everything, including vision nodes and the NAO layer |
| Runs on | Linux, Windows 11 | Ubuntu 24.04 (Jazzy) or 26.04 (Lyrical) |
| Choose it to | Try DialoStack, run demos, use it from the GUI | Modify the code, drive a robot, use the vision nodes |

- [Run with Docker](#run-with-docker): [quick start](#quick-start-any-system-with-docker) · [Linux](#linux) · [Windows 11](#windows-11) · [NVIDIA GPU](#gpu-acceleration-nvidia)
- [Build from source](#build-from-source)
- [Next steps](#next-steps)

## Run with Docker

The image bundles ROS 2 Jazzy, the dialogue core, the speech models and the web GUI. It runs on Linux and on Windows 11.

To build the image on ROS 2 Lyrical instead, pass the distro as a build argument:

```bash
docker build -f docker/Dockerfile --build-arg ROS_DISTRO=lyrical -t dialostack:lyrical .
```

### Quick start (any system with Docker)

With [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine installed, one command:

```bash
docker run -d --name dialostack -p 5173:5173 -p 9090:9090 ghcr.io/aquintan4/dialostack
```

Open **http://localhost:5173**, enter your LLM API key in **Configuration > LLM** (or pick Ollama) and press **Start engine**. Allow the microphone when the browser asks: the GUI page itself is the robot's microphone and speaker (the sidebar shows **Browser mic live**), so no audio setup is needed. From then on the container shows up in Docker Desktop, where it can be stopped and started again.

- **Local LLM:** on Docker Desktop, Ollama running on your machine is found with the GUI's default host `127.0.0.1`.
- **Keep the GUI tab open** while talking; browsers only allow the microphone on `localhost` or HTTPS.

The compose files below add what the quick start lacks: host audio routing, an NVIDIA GPU, and on Linux the host network so robots and other ROS 2 machines can discover the engine.

### Linux

Requires [Docker](https://docs.docker.com/engine/install/) and the Compose plugin.

```bash
curl -fsSLO https://raw.githubusercontent.com/aquintan4/DialoStack/main/docker-compose.yml
export GEMINI_API_KEY="your-key"   # or ANTHROPIC_API_KEY / OPENAI_API_KEY; or put it in a .env file next to docker-compose.yml
docker compose up
```

Open **http://localhost:5173**, check the configuration and press **Start engine**.

- **Audio:** by default the GUI page captures and plays the sound (**Configuration > Audio**, *This browser*). For *Local hardware*, the container also gets your desktop's microphone and speakers through the PulseAudio/PipeWire socket (`$XDG_RUNTIME_DIR/pulse/native`), the default on Ubuntu and most desktop distributions.
- **Local LLM:** run [Ollama](https://ollama.com) on the host and enable it in the GUI with host `127.0.0.1`; the container shares the host network.
- **ROS 2:** the dialogue action `/dialog/execute_task` is reachable from ROS 2 nodes on the host or the network (same `ROS_DOMAIN_ID`). To run the engine headless instead of the GUI: `docker compose run --rm dialostack ros2 launch ros2_dialog_manager main.launch.py`.
- The image does not include the optional vision nodes or the NAO packages; use a source build for those. For an NVIDIA GPU, see [GPU acceleration](#gpu-acceleration-nvidia).

To build the image yourself from a clone: `docker compose build`.

### Windows 11

Requires [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with its default WSL2 backend. In PowerShell:

```powershell
curl.exe -fsSLO https://raw.githubusercontent.com/aquintan4/DialoStack/main/docker-compose.windows.yml
$env:GEMINI_API_KEY = "your-key"   # or ANTHROPIC_API_KEY / OPENAI_API_KEY; or put it in a .env file next to the compose file
docker compose -f docker-compose.windows.yml up
```

Open **http://localhost:5173** and press **Start engine**.

- **Audio:** by default the GUI page captures and plays the sound, as in the quick start. For *Local hardware* routing (**Configuration > Audio**), the microphone and speakers of Windows reach the container through WSLg, built into Windows 11; allow microphone access for desktop apps in Windows privacy settings.
- **Local LLM:** install [Ollama for Windows](https://ollama.com/download) and select it in the GUI. The default host `127.0.0.1` is redirected to your PC, and Ollama uses your GPU.
- **ROS 2:** the Windows file publishes ports instead of sharing the host network, so the engine is not discoverable by robots or other ROS 2 machines. For that, build from source inside WSL2 (Ubuntu 24.04).

### GPU acceleration (NVIDIA)

The `-cuda` image runs speech recognition on an NVIDIA GPU, which makes the larger Whisper models (`medium`, `large-v3`) fast enough for live conversation. With the quick start, add `--gpus all` and the tag:

```bash
docker run -d --name dialostack --gpus all -p 5173:5173 -p 9090:9090 ghcr.io/aquintan4/dialostack:latest-cuda
```

With the compose files, download the GPU add-on next to yours and pass both. Linux:

```bash
curl -fsSLO https://raw.githubusercontent.com/aquintan4/DialoStack/main/docker-compose.gpu.yml
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

Windows 11 (PowerShell):

```powershell
curl.exe -fsSLO https://raw.githubusercontent.com/aquintan4/DialoStack/main/docker-compose.gpu.yml
docker compose -f docker-compose.windows.yml -f docker-compose.gpu.yml up
```

Nothing to set in the GUI: the STT device defaults to `auto`, which uses the GPU when there is one and the CPU otherwise. With the GPU, pick a larger model size in the **STT** tab. To force a device or compute type, set it there (`int8_float32` is fast on any NVIDIA GPU; `float16` only on RTX cards).

- **Windows 11:** a recent NVIDIA driver is all it needs; Docker Desktop passes the GPU through WSL2.
- **Linux:** install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
- A local LLM gets the GPU from Ollama itself, with or without this image.

## Build from source

### Prerequisites

- Ubuntu 24.04 with [ROS 2 Jazzy](https://docs.ros.org/en/jazzy/Installation.html), or Ubuntu 26.04 with [ROS 2 Lyrical](https://docs.ros.org/en/lyrical/Get-Started/Installation.html)
- Python ≥ 3.10
- An LLM provider: a [Gemini API key](https://aistudio.google.com/apikey) (the free tier works), a [Claude API key](https://console.anthropic.com) (a Claude.ai subscription does not include API access), an [OpenAI API key](https://platform.openai.com/api-keys) **or** a local [Ollama](https://ollama.com) install
- A microphone and speakers (any ALSA device)

### Install & build

```bash
mkdir -p ~/dialostack_ws/src && cd ~/dialostack_ws/src
git clone https://github.com/aquintan4/DialoStack.git
cd ..

# Python dependencies (faster-whisper, piper-tts, sounddevice, providers...)
pip install -r src/DialoStack/speech_io/requirements.txt
pip install -r src/DialoStack/ros2_llm_manager/config/requirements.txt
pip install -r src/DialoStack/vision_io/requirements.txt   # optional: vision nodes

colcon build --symlink-install
source install/setup.bash
```

> **Using a venv?** Sourcing the overlay reorders `PYTHONPATH` and hides the pip packages from the nodes. `activate.sh` fixes this. Open `src/DialoStack/activate.sh`, set the two variables at the top (your ROS distro and the venv path), then `source src/DialoStack/activate.sh` instead of `install/setup.bash` in every new terminal. It also exports `DIALOSTACK_MODELS_DIR`.

### Download the TTS voices

`text_to_speech_node` uses [Piper](https://github.com/rhasspy/piper) voices. One script fetches the default Spanish and English voices:

```bash
./src/DialoStack/scripts/download_models.sh
```

It downloads into `~/.local/share/dialostack/models` (override with `DIALOSTACK_MODELS_DIR`), where the nodes look by default. The shipped config references voices **by filename**, so you never edit a path. STT (faster-whisper) and the vision models download themselves on first run.

### Run the stack

```bash
export GEMINI_API_KEY="your-key"   # or ANTHROPIC_API_KEY + claude.enable, OPENAI_API_KEY + openai.enable, or enable Ollama in the config
ros2 launch ros2_dialog_manager main.launch.py
```

This brings up the four core nodes: STT, TTS, LLM manager and dialogue manager. Vision nodes and the robot layer are optional and launched separately.

### Run the web GUI

With the workspace sourced, `gui.sh` starts rosbridge and the GUI server, which then starts and stops the engine for you:

```bash
sudo apt install ros-$ROS_DISTRO-rosbridge-suite nodejs npm   # once
./src/DialoStack/gui.sh                      # open http://localhost:5173
./src/DialoStack/gui.sh --dev                # Vite with hot reload, for GUI development
```

## Next steps

- Open the GUI or send your first goal: see [Your first dialogue](../README.md#your-first-dialogue).
- Run the speech nodes on a robot's microphone and speaker: see [Audio routing](configuration.md#audio-routing).
- Tune every parameter: [configuration.md](configuration.md).
