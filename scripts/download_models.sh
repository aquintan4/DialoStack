#!/usr/bin/env bash
#
# Download the Piper TTS voices DialoStack ships with, into the models directory
# the nodes look in by default. Idempotent: existing files are skipped.
#
#   ./scripts/download_models.sh                # default voices (ES + EN)
#   DIALOSTACK_MODELS_DIR=/data/models ./scripts/download_models.sh
#
# Only Piper voices need fetching here. The STT (faster-whisper), lip-activity
# (MediaPipe) and emotion (Hugging Face) models download themselves on first run.
set -euo pipefail

MODELS_DIR="${DIALOSTACK_MODELS_DIR:-$HOME/.local/share/dialostack/models}"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# "<voice-name>:<huggingface-subpath>" — the default Spanish and English voices
# referenced by the shipped config. Add more here if you need other languages.
VOICES=(
  "es_ES-sharvard-medium:es/es_ES/sharvard/medium"
  "en_US-lessac-medium:en/en_US/lessac/medium"
)

fetch() {  # <url> <dest>
  local url="$1" dest="$2"
  if [ -f "$dest" ]; then
    echo "  = $(basename "$dest") (already present)"
    return
  fi
  echo "  + $(basename "$dest")"
  if command -v curl >/dev/null 2>&1; then
    curl -fSL --progress-bar "$url" -o "$dest.part"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --show-progress -O "$dest.part" "$url"
  else
    echo "ERROR: need 'curl' or 'wget' to download models." >&2
    exit 1
  fi
  mv "$dest.part" "$dest"
}

mkdir -p "$MODELS_DIR"
echo "Downloading Piper voices into: $MODELS_DIR"
for entry in "${VOICES[@]}"; do
  name="${entry%%:*}"; sub="${entry#*:}"
  fetch "$BASE/$sub/$name.onnx"      "$MODELS_DIR/$name.onnx"        # the voice
  fetch "$BASE/$sub/$name.onnx.json" "$MODELS_DIR/$name.onnx.json"  # its config
done

echo "Done."
echo "The nodes resolve voice filenames under this directory automatically."
echo "If you used a custom location, export it: DIALOSTACK_MODELS_DIR=$MODELS_DIR"
