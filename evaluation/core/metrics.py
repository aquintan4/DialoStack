"""
Metrics computation for dialog system evaluation.

Classes
-------
BinaryMetrics  — TP/FP/FN with precision / recall / F1.
MultiMetrics   — per-class and macro/weighted F1 for multi-class problems.

Functions
---------
confusion_matrix   — builds a label×label count dict.
print_confusion    — prints it as a compact ASCII table.
values_match       — normalised comparison for slot values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ==== BINARY METRICS (extraction / quiz) ====


@dataclass
class BinaryMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    errors: int = 0  # LLM returned None / unparseable

    def add_tp(self, n: int = 1) -> None:
        self.tp += n

    def add_fp(self, n: int = 1) -> None:
        self.fp += n

    def add_fn(self, n: int = 1) -> None:
        self.fn += n

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn

    def summary_row(self, label: str = "") -> list:
        return [
            label,
            self.support,
            f"{self.precision:.3f}",
            f"{self.recall:.3f}",
            f"{self.f1:.3f}",
            self.errors,
        ]


# ==== MULTI-CLASS METRICS (intent / task-mode / understanding) ====


@dataclass
class MultiMetrics:
    labels: list[str]
    _predicted: list[str] = field(default_factory=list, repr=False)
    _true: list[str] = field(default_factory=list, repr=False)
    errors: int = 0

    def record(self, predicted: Optional[str], true: str) -> None:
        if predicted is None:
            self.errors += 1
            return
        self._predicted.append(predicted)
        self._true.append(true)

    @property
    def accuracy(self) -> float:
        if not self._true:
            return 0.0
        return sum(p == t for p, t in zip(self._predicted, self._true)) / len(self._true)

    def per_class(self) -> dict[str, BinaryMetrics]:
        result: dict[str, BinaryMetrics] = {}
        for label in self.labels:
            m = BinaryMetrics()
            for p, t in zip(self._predicted, self._true):
                if t == label and p == label:
                    m.tp += 1
                elif t != label and p == label:
                    m.fp += 1
                elif t == label and p != label:
                    m.fn += 1
            result[label] = m
        return result

    def macro_f1(self) -> float:
        pc = self.per_class()
        if not pc:
            return 0.0
        return sum(m.f1 for m in pc.values()) / len(pc)

    def weighted_f1(self) -> float:
        if not self._true:
            return 0.0
        pc = self.per_class()
        total = len(self._true)
        return sum(
            pc[l].f1 * sum(1 for t in self._true if t == l) / total for l in self.labels if l in pc
        )

    def confusion_matrix(self) -> dict[str, dict[str, int]]:
        matrix = {l: {l2: 0 for l2 in self.labels} for l in self.labels}
        for p, t in zip(self._predicted, self._true):
            if t in matrix and p in matrix:
                matrix[t][p] += 1
        return matrix


# ==== VALUE COMPARISON ====


def values_match(got, expected, slot_type: str = "str") -> bool:
    """Compare extracted value with expected value, normalised."""
    if slot_type == "list_str":
        got_set = {str(v).lower().strip() for v in (got if isinstance(got, list) else [got])}
        exp_set = {
            str(v).lower().strip() for v in (expected if isinstance(expected, list) else [expected])
        }
        return got_set == exp_set
    return str(got).lower().strip() == str(expected).lower().strip()


def list_overlap(got: list, expected: list) -> tuple[int, int, int]:
    """Per-item TP/FP/FN for list_str slots."""
    got_set = {str(v).lower().strip() for v in got}
    exp_set = {str(v).lower().strip() for v in expected}
    tp = len(got_set & exp_set)
    fp = len(got_set - exp_set)
    fn = len(exp_set - got_set)
    return tp, fp, fn


# ==== CONFUSION MATRIX PRINTING ====


def print_confusion(matrix: dict[str, dict[str, int]], labels: list[str]) -> None:
    col_w = max(len(l) for l in labels) + 2
    header = f"{'':>{col_w}}" + "".join(f"{l:>{col_w}}" for l in labels)
    print(header)
    print("-" * len(header))
    for true_label in labels:
        row = f"{true_label:>{col_w}}"
        for pred_label in labels:
            row += f"{matrix[true_label][pred_label]:>{col_w}}"
        print(row)
