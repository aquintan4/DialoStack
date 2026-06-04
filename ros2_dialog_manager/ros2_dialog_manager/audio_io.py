"""
Audio I/O abstractions for the dialog system.

AudioIO   — abstract interface consumed by DialogFSM (listen / speak / clear_buffer).
RosAudioIO — concrete implementation that bridges ROS topics to the AudioIO contract.

Listening: blocks on a threading.Event signalled by /transcription messages.
Speaking:  delegates to the TTS action client via the node; supports barge-in
           through /user_speaking (the interrupt event is checked mid-playback).
"""

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dialog_manager_node import DialogManagerNode


class AudioIO(ABC):
    """Abstract audio interface consumed by DialogFSM."""

    @abstractmethod
    def speak(self, text: str) -> None: ...

    @abstractmethod
    def listen(self) -> str | None: ...

    @abstractmethod
    def clear_buffer(self) -> None: ...


class RosAudioIO(AudioIO):
    """
    Bridge between ROS topics and the AudioIO contract.

    Instantiated once per dialog goal and discarded afterwards.
    Thread-safe: on_transcription and on_user_speaking are called from ROS
    subscriber callbacks while listen() blocks on the FSM thread.
    """

    def __init__(self, node: "DialogManagerNode", timeout: float):
        self._node = node
        self._timeout = timeout
        self._text: str | None = None
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._interrupt_speech = threading.Event()

    # ==== TOPIC CALLBACKS (called from ROS executor threads) ====

    def on_transcription(self, text: str) -> None:
        with self._lock:
            self._text = text
            self._event.set()

    def on_user_speaking(self, speaking: bool) -> None:
        if speaking:
            self._interrupt_speech.set()
        else:
            self._interrupt_speech.clear()

    # ==== AUDIO IO CONTRACT ====

    def clear_buffer(self) -> None:
        with self._lock:
            self._text = None
            self._event.clear()

    def listen(self) -> str | None:
        self.clear_buffer()
        got_input = self._event.wait(timeout=self._timeout)
        with self._lock:
            return self._text if got_input else None

    def speak(self, text: str) -> None:
        # Reset barge-in flag before speaking. If the user barged in during TTS,
        # their transcription stays in the buffer for the next listen() call.
        self._interrupt_speech.clear()
        self._node._speak_sync(text, self._interrupt_speech)
