"""
RoleplayStrategy — the robot plays a character so the user can practise a
situation, then steps out of the role and scores them against a rubric.

The caller supplies the scene via resources_json. The content of the first
resource that parses as a JSON object with "scenario" and "role" is used:
    {"scenario": "Job interview for a robotics internship",
     "role": "The interviewer: demanding but kind",
     "user_goal": "Get the internship",            (optional)
     "criteria": ["Answers clearly", "Gives concrete examples"],
     "max_exchanges": 8}                           (optional)

Each user turn is classified first:
    continue  -> the character replies, staying in role
    coach     -> the user asks for help out of character: a short hint, then
                 the scene goes on
    end       -> the user wants to stop the practice
    scene_end -> the scene reached its natural end (e.g. the interview closed)
The scene resource is removed from the dialog context: every prompt injects
the context, and the character must not see the rubric (it would steer the
user toward the criteria instead of acting naturally). The prompts get the
scene explicitly, and only the evaluation sees the criteria.

The scene also ends after max_exchanges user turns (capped by the goal's
max_turns, so the evaluation always happens before the FSM aborts). On end
the transcript is scored per criterion (1-5) and the feedback is spoken.

current_data() returns:
    {"scenario": "...", "role": "...", "exchanges": k, "max_exchanges": N,
     "ended_by": "user|scene|limit|None",
     "scores": [{"criterion","score","evidence","comment"}],
     "average": float|None, "highlight": "...", "improve": "..."}
"""

import logging
import time  # TRACE

from ..utils import parse_loose_json
from .base import BaseDialogStrategy, FSMConfig, register_strategy

_DEFAULT_MAX_EXCHANGES = 10


@register_strategy("roleplay")
class RoleplayStrategy(BaseDialogStrategy):

    def __init__(self, llm, config: FSMConfig, ctx, request=None):
        super().__init__(llm, config, ctx, request)
        self._scene, scene_resource = self._parse_scene(ctx)
        if scene_resource is not None:
            ctx.resources = [r for r in ctx.resources if r is not scene_resource]
        self._max_exchanges = self._exchange_limit(self._scene, config)
        self._exchanges = 0
        self._history: list[dict] = []
        self._ended_by: str | None = None
        self._evaluation: dict = {}
        self._completed = False
        self._log = logging.getLogger("RoleplayStrategy")
        self._skip_intro: bool = (
            bool(getattr(request, "skip_intro", False)) if request else False
        )

    @staticmethod
    def _parse_scene(ctx) -> tuple[dict | None, object | None]:
        """The scene and the resource it came from, or (None, None)."""
        for resource in ctx.resources:
            content = (getattr(resource, "content", "") or "").strip()
            if not content:
                continue
            try:
                data = parse_loose_json(content)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            scenario = str(data.get("scenario") or "").strip()
            role = str(data.get("role") or "").strip()
            if not scenario or not role:
                continue
            criteria = []
            for c in data.get("criteria") or []:
                text = c.get("name") if isinstance(c, dict) else c
                if isinstance(text, str) and text.strip():
                    criteria.append(text.strip())
            try:
                max_exchanges = int(data.get("max_exchanges") or 0)
            except (TypeError, ValueError):
                max_exchanges = 0
            scene = {
                "scenario": scenario,
                "role": role,
                "user_goal": str(data.get("user_goal") or "").strip(),
                "criteria": criteria,
                "max_exchanges": max(0, max_exchanges),
            }
            return scene, resource
        return None, None

    @staticmethod
    def _exchange_limit(scene: dict | None, config: FSMConfig) -> int:
        limit = (scene or {}).get("max_exchanges") or _DEFAULT_MAX_EXCHANGES
        # The FSM aborts once max_turns is reached: close the scene on the last
        # allowed turn so the user still gets the evaluation.
        if config.max_turns > 0:
            limit = min(limit, config.max_turns)
        return limit

    # ==== LIFECYCLE ====

    def on_init(self, task: str) -> str:
        if not self._scene:
            raise ValueError(
                "RoleplayStrategy requires a resource whose content is a JSON object "
                "with at least 'scenario' and 'role'."
            )
        if not self._scene["criteria"]:
            raise ValueError(
                "RoleplayStrategy requires at least one evaluation criterion."
            )
        first_line = self._llm.roleplay_reply(self._scene, self._history, self._ctx)
        self._history.append({"role": "assistant", "content": first_line})
        if self._skip_intro:
            return first_line
        intro = self._llm.roleplay_intro(task, self._scene, self._ctx)
        return f"{intro} {first_line}"

    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]:
        cancel_result = self._cancel_pre_check(task, user_text, strict=False)
        if cancel_result is not None:
            return cancel_result

        self._exchanges += 1
        self._history.append({"role": "user", "content": user_text})
        intent = self._llm.classify_roleplay_turn(
            user_text, self._scene, self._history, self._ctx
        )
        # TRACE
        self._log.info(
            f"[TRACE] roleplay_turn n={self._exchanges}/{self._max_exchanges} intent={intent} | t={time.monotonic():.4f}"
        )
        # /TRACE

        if intent in ("end", "scene_end"):
            return self._finish(task, "user" if intent == "end" else "scene")
        if self._exchanges >= self._max_exchanges:
            return self._finish(task, "limit")

        if intent == "coach":
            hint = self._llm.roleplay_coach(
                user_text, self._scene, self._history, self._ctx
            )
            # Hints are out of character: kept out of the scene transcript.
            self._history.pop()
            return hint, False

        reply = self._llm.roleplay_reply(self._scene, self._history, self._ctx)
        self._history.append({"role": "assistant", "content": reply})
        return reply, False

    # ==== EVALUATION ====

    def _finish(self, task: str, ended_by: str) -> tuple[str, bool]:
        self._ended_by = ended_by
        self._evaluation = self._llm.evaluate_roleplay(
            self._scene, self._history, self._ctx
        )
        feedback = self._llm.roleplay_feedback(
            self._scene, self._evaluation, ended_by, self._ctx
        )
        self._evaluation["highlight"] = feedback["highlight"]
        self._evaluation["improve"] = feedback["improve"]
        self._completed = True
        return feedback["text"], True

    def _average(self) -> float | None:
        scores = [s["score"] for s in self._evaluation.get("scores", [])]
        return round(sum(scores) / len(scores), 2) if scores else None

    # ==== STATE ====

    def succeeded(self) -> bool:
        return self._completed and not self._user_cancelled

    def current_data(self) -> dict:
        scene = self._scene or {}
        return {
            "scenario": scene.get("scenario", ""),
            "role": scene.get("role", ""),
            "exchanges": self._exchanges,
            "max_exchanges": self._max_exchanges,
            "ended_by": self._ended_by,
            "scores": list(self._evaluation.get("scores", [])),
            "average": self._average(),
            "highlight": self._evaluation.get("highlight", ""),
            "improve": self._evaluation.get("improve", ""),
        }

    def current_phase(self) -> str:
        if self._completed:
            return "done"
        return f"scene_{self._exchanges}_of_{self._max_exchanges}"

    def turn_count(self) -> int:
        return self._exchanges
