# BargeIn — authoritative notice that the user interrupted the robot mid-speech.
#
# Published by the dialog manager the instant an ongoing TTS utterance is cut
# short because the user started speaking (true barge-in), detected by the
# action-level cancel in _speak_sync (the interrupt event fired, not a timeout).
#
# The Monitor GUI consumes this as the single source of truth for barge-in,
# instead of guessing from the timing of /is_speaking, /user_vad and
# /transcription — topics with no cross-ordering guarantee, which produced
# spurious barge-in marks on ordinary turns.

string  utterance   # the robot text that was cut short
uint32  spoken_ms   # how long the robot had been speaking when cut, in ms
