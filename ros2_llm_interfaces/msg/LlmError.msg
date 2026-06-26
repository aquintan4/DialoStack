# LlmError — a failed LLM inference, surfaced for operators and GUIs.
#
# Published by the LLM manager whenever a provider returns an unsuccessful
# GenerateResult (HTTP 4xx/5xx, timeout, lost connection, API error...). The
# dialog then falls back to a deterministic reply, so without this signal a
# failure is invisible: the conversation just looks dumb. The Monitor subscribes
# to /llm/error and shows the real cause (provider, model, code, message).
#
# Provider-agnostic on purpose: every backend maps its failure onto these
# fields, so the GUI needs no per-provider knowledge.

string provider     # "ollama", "gemini", ...
string model        # the model that failed, e.g. "llama3.2:3b"
string session_id   # which LLM session (e.g. dlg_nlu / dlg_nlg)
int32  code         # HTTP/status code when known, else 0
string error_type   # "http" | "timeout" | "connection" | "api" | "unknown"
string message      # human-readable detail (raw provider error)
