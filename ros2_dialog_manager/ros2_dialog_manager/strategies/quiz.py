"""
QuizStrategy — asks a sequence of questions with known answers and scores them.

The caller supplies questions and answers via resources_json. The content of
the first resource that parses as a JSON list of {"question","answer"} objects
is used as the question bank. If no valid resource is found, on_init raises.

Expected resource content:
    [{"question": "...", "answer": "..."}, ...]
    (also accepts "q"/"a" as short-form keys)

current_data() returns:
    {"total_questions": N, "current_question": k, "correct_answers": M, "results": [...]}
"""

import logging

from ..utils import parse_loose_json
from .base import BaseDialogStrategy, FSMConfig, register_strategy


@register_strategy("quiz")
class QuizStrategy(BaseDialogStrategy):

    def __init__(self, llm, config: FSMConfig, ctx, request=None):
        super().__init__(llm, config, ctx, request)
        self._questions: list[dict] = self._parse_questions(ctx)
        self._current_idx = 0
        self._results: list[dict] = []
        self._completed = False
        self._log = logging.getLogger("QuizStrategy")

    @staticmethod
    def _parse_questions(ctx) -> list[dict]:
        for resource in ctx.resources:
            content = (getattr(resource, "content", "") or "").strip()
            if not content:
                continue
            try:
                data = parse_loose_json(content)
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            items: list[dict] = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                q = entry.get("question") or entry.get("q")
                a = entry.get("answer") or entry.get("a")
                if isinstance(q, str) and q.strip() and a is not None:
                    items.append({"question": q.strip(), "answer": str(a).strip()})
            if items:
                return items
        return []

    def on_init(self, task: str) -> str:
        if not self._questions:
            raise ValueError(
                "QuizStrategy requires a resource with a JSON list of "
                "{'question','answer'} items in its content field."
            )
        intro = self._llm.quiz_opening(task, len(self._questions))
        return f"{intro} {self._questions[0]['question']}"

    def on_user_turn(self, task: str, user_text: str) -> tuple[str, bool]:
        cancel_result = self._cancel_pre_check(task, user_text, strict=False)
        if cancel_result is not None:
            return cancel_result

        current = self._questions[self._current_idx]
        evaluation = self._llm.evaluate_quiz_answer(
            question=current["question"],
            expected=current["answer"],
            given=user_text,
        )
        feedback = evaluation["feedback"]

        self._results.append(
            {
                "question": current["question"],
                "expected": current["answer"],
                "given": user_text,
                "correct": evaluation["correct"],
            }
        )
        self._current_idx += 1

        if self._current_idx >= len(self._questions):
            self._completed = True
            wrongs = [r["question"] for r in self._results if not r["correct"]]
            summary = self._llm.quiz_summary(
                task=task,
                correct=sum(1 for r in self._results if r["correct"]),
                total=len(self._questions),
                wrongs=wrongs,
            )
            return f"{feedback} {summary}", True

        next_question = self._questions[self._current_idx]["question"]
        reply = self._llm.quiz_next_question(
            feedback=feedback,
            n=self._current_idx + 1,
            total=len(self._questions),
            question=next_question,
        )
        return reply, False

    def succeeded(self) -> bool:
        return self._completed and not self._user_cancelled

    def current_data(self) -> dict:
        return {
            "total_questions": len(self._questions),
            "current_question": self._current_idx,
            "correct_answers": sum(1 for r in self._results if r["correct"]),
            "results": list(self._results),
        }

    def current_phase(self) -> str:
        if self._completed:
            return "done"
        return f"question_{self._current_idx + 1}_of_{len(self._questions)}"

    def turn_count(self) -> int:
        return len(self._results)
