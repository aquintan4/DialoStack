# AudioChunk — DialoStack's platform-agnostic raw-audio contract.
#
# A chunk of raw PCM audio exchanged between the speech nodes and whatever
# captures/plays sound (the built-in audio_bridge_node, a robot's own driver,
# or any third party). Anyone who publishes/consumes this message on the
# agreed topics (/audio_in for input, /audio_out for output) interoperates
# with DialoStack without depending on a particular robot or audio stack.

uint8[]  data         # raw interleaved PCM samples, little-endian
uint32   sample_rate  # samples per second, e.g. 16000 (STT) or 22050 (TTS)
uint8    channels     # number of interleaved channels (1 = mono)
string   encoding     # sample encoding; currently only "S16LE" is supported
