"""
ScriptedUserAudioIO — implements the production AudioIO interface without ROS.

speak()  → captures bot utterances in a list (no real TTS).
listen() → returns the next scripted user response, or None on exhaustion
           (simulates a timeout, which ends the dialog).
"""

import sys
import os

# AudioIO is imported after path_setup() in each benchmark script.
# This module defers the import to avoid order-of-import issues.


class ScriptedUserAudioIO:
    """
    Simulated audio IO for end-to-end dialog evaluation.

    Parameters
    ----------
    script : list[str]
        Ordered list of user responses. Must cover every listen() call the
        dialog will make; if it runs out, listen() returns None (timeout).
    verbose : bool
        Print bot/user turns to stdout while the dialog runs.
    """

    def __init__(self, script: list[str], verbose: bool = False):
        self._script = list(script)
        self._idx = 0
        self._verbose = verbose
        self._bot_utterances: list[str] = []
        self._user_utterances: list[str] = []

    # AudioIO contract

    def speak(self, text: str) -> None:
        self._bot_utterances.append(text)
        if self._verbose:
            print(f"    BOT : {text}")

    def listen(self) -> str | None:
        if self._idx >= len(self._script):
            if self._verbose:
                print("    USER: <timeout — script exhausted>")
            return None
        response = self._script[self._idx]
        self._idx += 1
        self._user_utterances.append(response)
        if self._verbose:
            print(f"    USER: {response}")
        return response

    def clear_buffer(self) -> None:
        pass

    # Inspection helpers

    @property
    def bot_utterances(self) -> list[str]:
        return list(self._bot_utterances)

    @property
    def user_utterances(self) -> list[str]:
        return list(self._user_utterances)

    @property
    def turns_consumed(self) -> int:
        return self._idx
