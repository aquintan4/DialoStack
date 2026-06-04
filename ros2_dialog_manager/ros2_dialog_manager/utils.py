"""
Stateless helpers shared across the dialog package.

  - clean_user_input:   ASR validation and noise filtering.
  - normalize_text:     locale-independent text normalisation.
  - local_cancel_check: fast-path cancel-intent detection (no LLM).
  - parse_loose_json:   tolerant JSON parsing for noisy LLM outputs.
"""

import json
import re
import unicodedata
from typing import Any

# Minimum number of recognisable words required to forward ASR output to the
# dialog system. One word is enough ("sí", "no", "domicilio", ...).
_MIN_WORDS = 1

# Pure filler or hallucinated transcripts. Anything in this set is silently
# discarded. Short affirmations like "ok" or "okay" are NOT included here:
# they are legitimate confirmations during the confirming phase.
# The list also catches recurrent Whisper hallucinations seen in production
# (YouTube-style outros) — those are multi-word and specific enough that real
# conversation almost never contains them.
_NOISE_PHRASES = frozenset(
    {
        "gracias por ver",
        "gracias por verlo",
        "gracias por su atencion",
        "suscribete",
        "no olvides suscribirte",
        "no olvides",
        "dale like",
        "dale me gusta",
        "subtitulos",
        "amara",
        "musica",
        "silencio",
        "aplausos",
        "continuara",
        "proxima semana",
        "nos vemos en el proximo",
        "proximo video",
        "proximos videos",
        "hasta la proxima vez",
        "hasta la proxima semana",
        "eh",
        "mm",
        "hmm",
    }
)

# Universal explicit cancel commands (language-independent).
# Language-specific cancel phrases are detected by the LLM via detect_cancel_intent.
_CANCEL_EXACT = frozenset(
    {
        "stop",
        "exit",
        "cancel",
        "quit",
        "abort",
    }
)

# Universally unambiguous cancel-coloured tokens.
_CANCEL_PATTERNS = re.compile(r"\b(stop|exit|cancel|quit|abort)\b")


def remove_accents(text: str) -> str:
    """Strip diacritics for locale-independent matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    text = remove_accents(text.lower().strip())
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_user_input(text: str) -> str | None:
    """
    Validate raw ASR output before passing it to the dialog system.

    Returns the original string if valid, or None if the input is empty, pure
    noise, or below the minimum word count. The original (non-normalised)
    string is returned so downstream NLU still sees accents and casing.
    """
    text = text.strip()
    if not text:
        return None

    normalized = normalize_text(text)
    if not normalized:
        return None

    if any(phrase in normalized for phrase in _NOISE_PHRASES):
        return None

    words = [w for w in normalized.split() if re.search(r"[a-z0-9]", w)]
    if len(words) < _MIN_WORDS:
        return None

    return text


def local_cancel_check(text: str, strict: bool = False) -> bool | None:
    """
    Fast local cancel detection that avoids an LLM call when possible.

    Returns:
        True   → definite cancel.
        False  → definite non-cancel.
        None   → ambiguous, fall back to the LLM (only in non-strict mode).

    strict=True is used when the user is answering a choice question where
    partial cancel-like words are routine. In strict mode only exact-command
    matches return True; anything else returns False (no LLM fallback).

    Detection order is deliberate: an exact cancel command wins over any other
    interpretation. This prevents shadowing such as "cancela para mí" being
    misread as non-cancel due to "para mí" appearing inside it.
    """
    normalized = normalize_text(text)

    # 1. Exact cancel command → definite cancel.
    if normalized in _CANCEL_EXACT:
        return True

    if strict:
        return False

    # 2. Cancel-coloured token present → ambiguous, ask the LLM.
    if _CANCEL_PATTERNS.search(normalized):
        return None

    # 3. No cancel signal at all.
    return False


def to_snake_case(name: str) -> str:
    """Normalise a slot name to snake_case.
    Handles spaces, hyphens, CamelCase and non-alphanumeric characters."""
    name = re.sub(r"[\s\-]+", "_", name.strip())
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = name.lower()
    name = re.sub(r"[^\w]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "slot"


def parse_loose_json(raw: Any) -> Any:
    """
    Tolerant JSON parser used for LLM outputs.

    Strips markdown fences, locates the outermost container (object or array),
    removes trailing commas, then delegates to json.loads. Returns whatever
    json.loads produces (dict or list). Raises ValueError on failure.
    """
    if isinstance(raw, (dict, list)):
        return raw

    text = re.sub(r"```json|```", "", str(raw)).strip()

    # Find the outermost container — prefer whichever appears first.
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates = [s for s in (obj_start, arr_start) if s != -1]
    if not candidates:
        raise ValueError("No JSON object or array found in payload")
    start = min(candidates)

    if text[start] == "{":
        end_char = "}"
    else:
        end_char = "]"
    end = text.rfind(end_char)
    if end == -1 or end < start:
        raise ValueError(f"Unterminated JSON {end_char}")

    candidate = re.sub(r",\s*([\]}])", r"\1", text[start : end + 1])
    return json.loads(candidate)
