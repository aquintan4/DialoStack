#!/usr/bin/env python3
"""
DialoStack GUI server.

Modes
-----
Production (default):
    python3 server.py [port] [web_dir]
    Serves the built SPA at <web_dir> and exposes /api/* on the same port.

Dev mode (alongside Vite):
    python3 server.py --api-only [port]
    Only serves /api/* - Vite proxies requests here from the dev server.

API
---
    GET  /api/engine/status     {'state', 'pid', 'log'}
    POST /api/engine/start      body {'config': {...}} -> {'ok', 'error'}
    POST /api/engine/stop       -> {'ok'}
    POST /api/engine/keepalive  -> {'ok'}
    GET  /api/engine/log        -> {'log'}
    POST /api/config/yaml       body {'config': {...}} -> {'yaml'}
    GET  /api/prompts           -> {'prompts': {key: template}, 'available'}
    POST /api/prompts/yaml      body {'overrides': {...}, 'mode': 'full'|'overrides'} -> {'yaml'}
"""

import argparse
import http.server
import json
import os
import signal
import string
import subprocess
import threading
import time
import urllib.error
import urllib.request

import yaml

GUI_PARAMS_FILE = "/tmp/dialostack_gui_params.yaml"
ENGINE_LOG_FILE = "/tmp/dialostack_engine.log"
# Stop the engine if the browser disappears. Must be generous: browsers throttle
# background-tab timers to ~1/min, so a low value would kill the engine just by
# switching windows.
KEEPALIVE_TIMEOUT = 300  # seconds
STARTUP_GRACE = 5  # seconds before 'starting' promotes to 'running'
ENGINE_PATTERN = "ros2_dialog_manager.*main.launch"
LOG_TAIL_LINES = 80


# ==== CONFIG SANITISATION ====
# The config arrives from the browser, so every value gets coerced to the type
# the ROS nodes expect; anything missing or malformed falls back to a default.


def _num(value, fallback, lo=None, hi=None, integer=False):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return fallback
    if n != n:  # NaN
        return fallback
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return int(n) if integer else n


def _text(value, fallback=""):
    return str(value).strip() if isinstance(value, (str, int, float)) else fallback


def _flag(value, fallback=False):
    return bool(value) if isinstance(value, bool) else fallback


# ==== PROMPTS: ENGINE DEFAULTS AND OVERRIDE VALIDATION ====
# The default prompts live in prompts.yaml of the ros2_dialog_manager package.
# The GUI can override specific templates but NEVER touches the file: valid
# overrides are injected as node parameters (they win when applied afterwards).
# Here are the defaults (to serve them) and the validation that prevents a broken
# override from reaching the engine.


def _default_prompts() -> dict:
    """Read the default templates from the installed prompts.yaml."""
    try:
        from ament_index_python.packages import get_package_share_directory

        path = os.path.join(
            get_package_share_directory("ros2_dialog_manager"), "config", "prompts.yaml"
        )
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        prompts = (
            (data.get("dialog_manager_node") or {}).get("ros__parameters") or {}
        ).get("prompts") or {}
        return {k: v for k, v in prompts.items() if isinstance(v, str)}
    except Exception:
        return {}


def _field_names(tpl: str):
    """(placeholders, ok). Same semantics as the node's boot-time validation."""
    names = set()
    try:
        for _, field, _, _ in string.Formatter().parse(tpl):
            if field:
                names.add(field.split(".")[0].split("[")[0])
    except ValueError:
        return set(), False
    return names, True


def _valid_prompt_override(template: str, default: str) -> bool:
    """True if the override is safe: well-formed braces and no placeholders the
    default does not use (avoids the runtime KeyError in PromptBuilder.format)."""
    names, ok = _field_names(template)
    if not ok or any(not n.isidentifier() for n in names):
        return False
    allowed, ok_def = _field_names(default)
    allowed = (allowed if ok_def else set()) | {"language"}
    return names <= allowed


# Dumper that uses block scalars ('|') for multiline templates, so the exported
# prompts.yaml is readable and editable like the original.
class _BlockDumper(yaml.SafeDumper):
    pass


def _str_block_representer(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_BlockDumper.add_representer(str, _str_block_representer)


def prompts_yaml(overrides: dict, mode: str) -> str:
    """Prompt YAML to export. mode='full' gives defaults + valid overrides (a
    drop-in replacement for prompts.yaml); mode='overrides' gives only the
    overrides (extra params to apply after prompts.yaml). Invalid ones are dropped."""
    defaults = _default_prompts()
    valid = {}
    for key, val in (overrides or {}).items():
        default = defaults.get(key)
        if (
            isinstance(val, str)
            and val.strip()
            and default is not None
            and val != default
            and _valid_prompt_override(val, default)
        ):
            valid[key] = val

    merged = {**defaults, **valid} if mode == "full" else valid
    doc = {"dialog_manager_node": {"ros__parameters": {"prompts": merged}}}

    header = "# Generated by DialoStack GUI - do not edit the GUI copy, edit here\n"
    header += (
        "# Full prompt set (engine defaults + your overrides). Drop-in "
        "replacement for prompts.yaml.\n"
        if mode == "full"
        else "# Prompt overrides only. Pass as an extra --params-file "
        "AFTER prompts.yaml.\n"
    )
    return header + yaml.dump(
        doc,
        Dumper=_BlockDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def build_params(config: dict) -> dict:
    """Build the ROS 2 params dict (node -> ros__parameters) from a GUI config."""
    llm = config.get("llm") or {}
    dialog = config.get("dialog") or {}
    stt = config.get("stt") or {}
    tts = config.get("tts") or {}

    stt_params = {
        "input_device": _text(stt.get("input_device")),
        "model_size": _text(stt.get("model_size"), "small"),
        "language": _text(stt.get("language"), "es"),
        "device": _text(stt.get("device"), "cpu"),
        "compute_type": _text(stt.get("compute_type"), "int8"),
        "cpu_threads": _num(stt.get("cpu_threads"), 4, 1, 64, integer=True),
        "sample_rate": _num(stt.get("sample_rate"), 16000, integer=True),
        "vad_threshold": _num(stt.get("vad_threshold"), 0.5, 0.0, 1.0),
        "grace_period": _num(stt.get("grace_period"), 0.8, 0.0),
        "max_phrase_secs": _num(stt.get("max_phrase_secs"), 8.0, 1.0),
        "silent_mode": _flag(stt.get("silent_mode")),
    }

    tts_params = {
        "sample_rate": _num(tts.get("sample_rate"), 22050, integer=True),
        "audio_device": _text(tts.get("audio_device"), "default"),
    }
    tts_model_path = _text(tts.get("model_path"))
    if tts_model_path:
        # Only override when set - otherwise the node keeps its app_params value
        tts_params["model_path"] = tts_model_path

    provider = "ollama" if llm.get("provider") == "ollama" else "gemini"
    llm_timeout = _num(llm.get("timeout"), 60.0, 1.0, 3600.0)
    llm_model = _text(
        llm.get("model"), "gemini-2.5-flash" if provider == "gemini" else "qwen2.5"
    )

    if provider == "gemini":
        gemini = {"enable": True, "model": llm_model, "timeout": llm_timeout}
        api_key = _text(llm.get("gemini_api_key"))
        if api_key:
            gemini["api_key"] = api_key
        ollama = {"enable": False}
    else:
        gemini = {"enable": False}
        ollama = {
            "enable": True,
            "host": _text(llm.get("ollama_host"), "127.0.0.1"),
            "port": _num(llm.get("ollama_port"), 11434, 1, 65535, integer=True),
            "model": llm_model,
            "timeout": llm_timeout,
        }

    llm_params = {
        "default_provider": provider,
        "max_concurrent": _num(llm.get("max_concurrent"), 4, 1, 64, integer=True),
        "silent_mode": _flag(llm.get("silent_mode")),
        "gemini": gemini,
        "ollama": ollama,
    }

    raw_acks = dialog.get("ack_phrases")
    ack_phrases = (
        [str(p).strip() for p in raw_acks if str(p).strip()]
        if isinstance(raw_acks, list)
        else []
    )
    if not ack_phrases:
        ack_phrases = ["Entendido."]

    dialog_params = {
        "language": _text(dialog.get("language"), "Spanish"),
        "history_max_turns": _num(
            dialog.get("history_max_turns"), 200, 1, integer=True
        ),
        "ack_phrases": ack_phrases,
        "wait_timeout": _num(dialog.get("wait_timeout"), 20.0, 1.0),
        "llm_timeout": _num(dialog.get("llm_timeout"), 120.0, 1.0),
        "tts_timeout": _num(dialog.get("tts_timeout"), 60.0, 1.0),
        "timeout_prompt": _text(dialog.get("timeout_prompt"), "¿Sigues ahí?"),
        "max_timeouts": _num(dialog.get("max_timeouts"), 2, 1, integer=True),
        "max_unclear": _num(dialog.get("max_unclear"), 3, 1, integer=True),
        "max_attempts": _num(dialog.get("max_attempts"), 3, 1, integer=True),
        "silent_mode": _flag(dialog.get("silent_mode")),
        "conversation_log_path": _text(dialog.get("conversation_log_path")),
        "conversation_log_max_mb": _num(
            dialog.get("conversation_log_max_mb"), 10.0, 0.0
        ),
    }

    # Prompt overrides: only those that differ from the default and pass
    # validation. Invalid or unknown ones are dropped silently, so the engine
    # always starts with the default template (no risk of breaking it).
    dialog_node_params = dialog_params
    raw_prompts = config.get("prompts")
    if isinstance(raw_prompts, dict):
        defaults = _default_prompts()
        overrides = {}
        for key, val in raw_prompts.items():
            default = defaults.get(key)
            if not isinstance(val, str) or not val.strip() or default is None:
                continue
            if val != default and _valid_prompt_override(val, default):
                overrides[key] = val
        if overrides:
            dialog_node_params = {**dialog_params, "prompts": overrides}

    return {
        "speech_to_text_node": {"ros__parameters": stt_params},
        "text_to_speech_node": {"ros__parameters": tts_params},
        "llm_manager_node": {"ros__parameters": llm_params},
        "dialog_manager_node": {"ros__parameters": dialog_node_params},
    }


def params_yaml(config: dict) -> str:
    return "# Generated by DialoStack GUI - do not edit manually\n" + yaml.safe_dump(
        build_params(config),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


# ==== MICROPHONE (HARDWARE MUTE VIA PIPEWIRE) ====
# Mutes the system default audio source with wpctl: the dialogue engine is not
# touched, it simply stops receiving audio.

MIC_SOURCE = "@DEFAULT_AUDIO_SOURCE@"


def _mic_status() -> dict:
    try:
        out = subprocess.run(
            ["wpctl", "get-volume", MIC_SOURCE],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode != 0:
            return {"available": False, "muted": False}
        return {"available": True, "muted": "MUTED" in out.stdout}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"available": False, "muted": False}


def _mic_set_mute(muted: bool) -> dict:
    try:
        subprocess.run(
            ["wpctl", "set-mute", MIC_SOURCE, "1" if muted else "0"],
            capture_output=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return _mic_status()


def _check_llm_provider(llm: dict):
    """Return an error message if the LLM provider is not usable."""
    provider = "ollama" if llm.get("provider") == "ollama" else "gemini"

    if provider == "gemini":
        if not _text(llm.get("gemini_api_key")) and not os.environ.get(
            "GEMINI_API_KEY"
        ):
            return (
                "Gemini has no API key: enter it in Configuration > LLM > "
                "API Key, or export it (GEMINI_API_KEY) before launching gui.sh"
            )
        return None

    host = _text(llm.get("ollama_host"), "127.0.0.1")
    port = _num(llm.get("ollama_port"), 11434, 1, 65535, integer=True)
    try:
        urllib.request.urlopen(f"http://{host}:{port}/api/version", timeout=2)
    except (urllib.error.URLError, OSError):
        return (
            f"Ollama is not responding at {host}:{port}. Start the server "
            f"(`ollama serve`) or switch provider in Configuration > LLM"
        )
    return None


# ==== ENGINE MANAGER ====


class EngineManager:
    """Owns the `ros2 launch` process: lifecycle, log file and browser watchdog."""

    def __init__(self):
        self._proc = None
        self._state = "stopped"  # 'stopped' | 'starting' | 'running' | 'error'
        self._stop_reason = None  # None | 'manual' | 'watchdog' | 'crash'
        self._lock = threading.Lock()
        self._log_fh = None
        self._last_keepalive = time.time()
        self._kill_stale()
        threading.Thread(target=self._watchdog, daemon=True).start()

    # ---- public ----

    def status(self) -> dict:
        with self._lock:
            self._refresh()
            return {
                "state": self._state,
                "pid": self._proc.pid if self._proc else None,
                "stop_reason": self._stop_reason,
                "log": ENGINE_LOG_FILE,
            }

    def start(self, config: dict):
        """Returns (ok, error_message)."""
        with self._lock:
            self._refresh()
            if self._state in ("running", "starting"):
                return False, "The engine is already running"
            if self._external_engine_running():
                return False, (
                    "An engine is running outside the GUI "
                    "(use `pkill -f main.launch.py` to stop it)"
                )

            # Without a usable LLM provider the engine starts but the dialogue
            # stays mute - better to fail here with a useful message than to
            # start an unusable engine.
            err = _check_llm_provider(config.get("llm") or {})
            if err:
                return False, err

            try:
                self._write_params_file(config)
            except OSError as exc:
                return False, f"Could not write the params file: {exc}"

            # Inherit the full environment so the ROS nodes can find venv
            # packages (sounddevice, faster-whisper...).
            env = dict(os.environ)
            env["DIALOSTACK_GUI_PARAMS"] = GUI_PARAMS_FILE

            try:
                self._open_log(env)
                self._proc = subprocess.Popen(
                    ["ros2", "launch", "ros2_dialog_manager", "main.launch.py"],
                    env=env,
                    stdout=self._log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except FileNotFoundError:
                return False, "`ros2` not found - is ROS 2 sourced in the environment?"
            except Exception as exc:
                return False, str(exc)

            self._state = "starting"
            self._stop_reason = None
            self._last_keepalive = time.time()
            threading.Thread(target=self._await_ready, daemon=True).start()
            return True, None

    def stop(self):
        with self._lock:
            self._kill()
            self._stop_reason = "manual"

    def keepalive(self):
        with self._lock:
            self._last_keepalive = time.time()

    def shutdown(self):
        with self._lock:
            self._kill()
            if self._log_fh:
                self._log_fh.close()
                self._log_fh = None

    # ---- private (lock held unless noted) ----

    @staticmethod
    def _engine_pids():
        try:
            result = subprocess.run(
                ["pgrep", "-f", ENGINE_PATTERN], capture_output=True, text=True
            )
            return [int(p) for p in result.stdout.split() if p.strip()]
        except FileNotFoundError:
            return []  # pgrep not available

    def _external_engine_running(self) -> bool:
        own = self._proc.pid if self._proc else None
        return any(pid != own for pid in self._engine_pids())

    def _kill_stale(self):
        """Kill engine processes left over from a previous GUI run (init only)."""
        pids = self._engine_pids()
        for pid in pids:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
        if pids:
            time.sleep(1)
            print(f"[engine] killed stale engine PIDs: {pids}", flush=True)

    @staticmethod
    def _write_params_file(config: dict):
        # 0600: the file may contain an API key
        fd = os.open(GUI_PARAMS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(params_yaml(config))

    def _open_log(self, env: dict):
        if self._log_fh:
            self._log_fh.close()
        self._log_fh = open(ENGINE_LOG_FILE, "w", encoding="utf-8")
        self._log_fh.write(
            f"--- DialoStack engine start ---\n"
            f'PATH={env.get("PATH", "")}\n'
            f'PYTHONPATH={env.get("PYTHONPATH", "")}\n'
            f'AMENT_PREFIX_PATH={env.get("AMENT_PREFIX_PATH", "")}\n'
            f'DIALOSTACK_GUI_PARAMS={env.get("DIALOSTACK_GUI_PARAMS", "")}\n'
            f"-------------------------------\n"
        )
        self._log_fh.flush()

    def _refresh(self):
        """Detect if the process died since the last query."""
        if self._proc is not None and self._proc.poll() is not None:
            rc = self._proc.returncode
            self._proc = None
            # SIGTERM (rc == -15) is a clean stop, anything else is an error.
            if rc in (0, -signal.SIGTERM):
                self._state = "stopped"
            else:
                self._state = "error"
                self._stop_reason = "crash"

    def _await_ready(self):
        """After a fixed grace period, promote 'starting' -> 'running'."""
        time.sleep(STARTUP_GRACE)
        with self._lock:
            self._refresh()
            if self._state == "starting":
                self._state = "running"

    def _kill(self):
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        self._proc = None
        self._state = "stopped"

    def _watchdog(self):
        """Stop the engine if the browser stops sending keepalives."""
        while True:
            time.sleep(5)
            with self._lock:
                self._refresh()
                stale = time.time() - self._last_keepalive > KEEPALIVE_TIMEOUT
                if stale and self._state in ("starting", "running"):
                    print("[watchdog] browser gone - stopping engine", flush=True)
                    self._kill()
                    self._stop_reason = "watchdog"


# Created in main(): instantiating it has side effects (kills orphan engines,
# starts the watchdog), which must not fire on module import.
_engine = None


# ==== HTTP HANDLER ====


class SPAHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._route("GET")
            return
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._route("POST")
        else:
            self.send_error(405)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _route(self, method):
        route = self.path.split("?")[0]
        if route == "/api/engine/status" and method == "GET":
            self._json(_engine.status())
        elif route == "/api/engine/start" and method == "POST":
            ok, err = _engine.start(self._body_json().get("config") or {})
            self._json({"ok": ok, "error": err})
        elif route == "/api/engine/stop" and method == "POST":
            _engine.stop()
            self._json({"ok": True})
        elif route == "/api/engine/keepalive" and method == "POST":
            _engine.keepalive()
            self._json({"ok": True})
        elif route == "/api/engine/log" and method == "GET":
            self._json({"log": self._log_tail()})
        elif route == "/api/config/yaml" and method == "POST":
            self._json({"yaml": params_yaml(self._body_json().get("config") or {})})
        elif route == "/api/prompts" and method == "GET":
            defaults = _default_prompts()
            self._json({"prompts": defaults, "available": bool(defaults)})
        elif route == "/api/prompts/yaml" and method == "POST":
            body = self._body_json()
            overrides = body.get("overrides")
            mode = "overrides" if body.get("mode") == "overrides" else "full"
            self._json(
                {
                    "yaml": prompts_yaml(
                        overrides if isinstance(overrides, dict) else {}, mode
                    )
                }
            )
        elif route == "/api/mic/status" and method == "GET":
            self._json(_mic_status())
        elif route == "/api/mic/mute" and method == "POST":
            self._json(_mic_set_mute(bool(self._body_json().get("muted"))))
        else:
            self._json({"error": "Not found"}, 404)

    @staticmethod
    def _log_tail() -> str:
        try:
            with open(ENGINE_LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
                return "".join(fh.readlines()[-LOG_TAIL_LINES:])
        except FileNotFoundError:
            return "(no log yet)"

    def _body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser closed the connection mid-response

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *_):
        pass


class APIOnlyHandler(SPAHandler):
    """Only routes /api/* - used alongside Vite in dev mode."""

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._route("GET")
        else:
            self._json({"error": "Not found"}, 404)


# ==== ENTRY POINT ====


def main():
    global _engine
    parser = argparse.ArgumentParser(description="DialoStack GUI server")
    parser.add_argument("port", nargs="?", type=int, default=5173)
    parser.add_argument("web_dir", nargs="?", default=".")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="serve only /api/* (dev mode, Vite serves the SPA)",
    )
    args = parser.parse_args()

    if not args.api_only:
        os.chdir(args.web_dir)

    _engine = EngineManager()

    handler = APIOnlyHandler if args.api_only else SPAHandler
    label = "API server" if args.api_only else "Server"
    print(f"{label} on http://0.0.0.0:{args.port}", flush=True)

    # Treat SIGTERM the same as Ctrl+C so the finally block always runs
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    server = http.server.ThreadingHTTPServer(("", args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[server] shutting down engine…", flush=True)
        _engine.shutdown()


if __name__ == "__main__":
    main()
