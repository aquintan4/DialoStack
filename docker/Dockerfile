# DialoStack runtime image: the dialogue core (dialog manager, LLM manager,
# speech I/O), rosbridge and the web GUI, with the default speech models baked
# in so the first start needs no downloads.
#
#   docker build -f docker/Dockerfile -t dialostack .
#   docker build -f docker/Dockerfile --build-arg VARIANT=cuda -t dialostack:cuda .
#
# The cuda variant adds the CUDA 12 / cuDNN 9 libraries that faster-whisper
# needs to run on an NVIDIA GPU (select device "cuda" in the GUI's STT tab).
# The GPU driver itself comes from the host through the NVIDIA runtime.
#
# Not included: vision_io (optional camera layer), the NAO packages and the
# BehaviorTree client. Build them from source on top of this image if needed.

ARG ROS_DISTRO=jazzy
ARG VARIANT=cpu

# ==== GUI BUILD ====
FROM node:20-slim AS gui
WORKDIR /gui
COPY dialostack_gui/package.json dialostack_gui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dialostack_gui/ ./
RUN npm run build

# ==== RUNTIME ====
FROM ros:${ROS_DISTRO}-ros-base
ARG ROS_DISTRO
ARG VARIANT

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_NO_CACHE_DIR=1 \
    DIALOSTACK_MODELS_DIR=/opt/dialostack/models

# rosbridge for the GUI, PortAudio + the ALSA->PulseAudio plugin for audio
# (works with PipeWire's pulse socket too), procps for the GUI engine manager.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-${ROS_DISTRO}-rosbridge-server \
        python3-pip python3-yaml \
        libportaudio2 libasound2-plugins pulseaudio-utils alsa-utils \
        procps curl \
    && rm -rf /var/lib/apt/lists/*
COPY docker/asound.conf /etc/asound.conf

# Python dependencies. CPU-only torch keeps the image gigabytes smaller; the
# pinned setuptools is skipped because the system one (used by colcon) cannot
# be replaced by pip. --ignore-installed installs next to the apt packages
# instead of upgrading them: Debian's have no RECORD file (Ubuntu 26.04 ships
# typing_extensions that way), so pip cannot uninstall them.
COPY speech_io/requirements.txt /tmp/req/speech_io.txt
COPY ros2_llm_manager/config/requirements.txt /tmp/req/llm.txt
RUN grep -hE '^(torch|torchaudio|torchvision)==' /tmp/req/speech_io.txt > /tmp/req/torch.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu -r /tmp/req/torch.txt \
    && grep -hvE '^setuptools==' /tmp/req/speech_io.txt /tmp/req/llm.txt > /tmp/req/all.txt \
    && pip install --ignore-installed -r /tmp/req/all.txt \
    && rm -rf /tmp/req

# GPU variant: cuBLAS and cuDNN from pip (what CTranslate2 links against),
# registered with the dynamic linker. Silero VAD stays on the CPU torch.
RUN if [ "$VARIANT" = "cuda" ]; then \
        pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" \
        && python3 -c "import nvidia.cublas.lib as b, nvidia.cudnn.lib as d; print(b.__path__[0]); print(d.__path__[0])" \
            > /etc/ld.so.conf.d/nvidia-pip.conf \
        && ldconfig; \
    fi

# Default models: Piper voices (ES + EN), Silero VAD and Whisper "small", loaded
# exactly as speech_to_text_node does so they land in the same caches.
COPY scripts/download_models.sh /tmp/download_models.sh
RUN /tmp/download_models.sh \
    && python3 -c "import torch; torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', trust_repo=True)" \
    && python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" \
    && rm /tmp/download_models.sh

# Workspace: the repo root is the colcon workspace, so gui.sh finds install/.
WORKDIR /opt/dialostack
COPY . .
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
    && colcon build \
        --packages-up-to ros2_dialog_manager ros2_llm_manager speech_io \
        --event-handlers console_direct- \
    && rm -rf build log
COPY --from=gui /gui/dist dialostack_gui/dist

# GUI + API, and rosbridge (the GUI's live connection). Declared so Docker
# Desktop offers them in its Run dialog.
EXPOSE 5173 9090

COPY docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/opt/dialostack/gui.sh"]
