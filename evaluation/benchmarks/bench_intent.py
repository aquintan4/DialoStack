"""
Benchmark: intent classification in the confirmation phase.

Measures whether the system correctly classifies the user intent into:
  confirms | corrects | question | unclear

Metrics:
  - Global accuracy
  - Per-class precision / recall / F1
  - Macro-F1 and Weighted-F1
  - Confusion matrix
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.path_setup import setup_path, load_config, load_prompts, resolve_path

setup_path()

from core.llm_adapter import make_infer_fn
from core.metrics import MultiMetrics, print_confusion
from core.report import print_section, print_table, print_summary, save_json

from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.prompt_builder import PromptBuilder
from ros2_dialog_manager.dialog_frame import DialogFrame

_LABELS = ["confirms", "corrects", "question", "unclear"]


def _build_frame_with_values(slot_schema: dict, frame_filled: dict) -> DialogFrame:
    frame = DialogFrame.from_slots_json(json.dumps(slot_schema))
    if frame_filled:
        frame.try_update(frame_filled)
    return frame


def run(cfg: dict, dataset_path: str, verbose: bool = False) -> dict:
    prompts_path = resolve_path(cfg["prompts_yaml"])
    templates = load_prompts(prompts_path)
    language = cfg.get("dialog", {}).get("language", "Spanish")
    history_max = cfg.get("dialog", {}).get("history_max_turns", 200)

    infer_fn = make_infer_fn(cfg)
    pb = PromptBuilder(templates, language=language)
    llm = LLMDialogClient(
        nlu_session_id="eval_nlu",
        nlg_session_id="eval_nlg",
        infer_fn=infer_fn,
        prompt_builder=pb,
        language=language,
        history_max_turns=history_max,
    )

    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)
    cases = dataset.get("cases", [])

    metrics = MultiMetrics(labels=_LABELS)
    case_results = []

    print_section("BENCHMARK: Intent classification (confirming phase)")
    print(f"  Dataset : {os.path.basename(dataset_path)}")
    print(f"  Cases   : {len(cases)}")
    print(f"  Provider: {cfg['llm']['provider']} / {cfg['llm']['model']}\n")

    total = len(cases)
    for idx, case in enumerate(cases, 1):
        cid = case["id"]
        user_text = case["user_text"]
        expected_intent = case["expected_intent"]
        slot_schema = case["slot_schema"]
        frame_filled = case.get("frame_filled", {})

        print(f"  [{idx}/{total}] {cid} ...", end="", flush=True)
        if verbose:
            print(f"\n         {case['description']}")
            print(f"         user: '{user_text}'")
            print(f"         expected: {expected_intent}")

        try:
            frame = _build_frame_with_values(slot_schema, frame_filled)
        except Exception as exc:
            metrics.errors += 1
            case_results.append({"id": cid, "status": "frame_error", "error": str(exc)})
            continue

        t0 = time.monotonic()
        try:
            intent, corrections = llm.classify_intent(user_text, frame, ctx=None)
        except Exception as exc:
            metrics.errors += 1
            case_results.append({"id": cid, "status": "llm_error", "error": str(exc)})
            continue
        elapsed = time.monotonic() - t0

        metrics.record(intent, expected_intent)
        correct = intent == expected_intent

        case_results.append(
            {
                "id": cid,
                "description": case["description"],
                "user_text": user_text,
                "expected": expected_intent,
                "got": intent,
                "correct": correct,
                "corrections": corrections,
                "latency_s": round(elapsed, 3),
            }
        )

        mark = "✓" if correct else "✗"
        print(f" {intent}  {mark}  ({elapsed:.2f}s)", flush=True)
        if verbose:
            print(f"         got: {intent}")

    # ==== Summary ====
    pc = metrics.per_class()
    print_section("GLOBAL RESULTS")
    print_summary("Accuracy", f"{metrics.accuracy:.3f}")
    print_summary("Macro-F1", f"{metrics.macro_f1():.3f}")
    print_summary("Weighted-F1", f"{metrics.weighted_f1():.3f}")
    print_summary("LLM errors", metrics.errors)

    # Per-class table
    class_rows = []
    for label in _LABELS:
        m = pc[label]
        class_rows.append(
            [label, m.support, f"{m.precision:.3f}", f"{m.recall:.3f}", f"{m.f1:.3f}"]
        )
    print_table(
        ["Class", "Support", "Precision", "Recall", "F1"],
        class_rows,
        title="Per-class metrics",
    )

    # Confusion matrix
    print("\n  Confusion matrix (rows=true, columns=predicted):")
    print_confusion(metrics.confusion_matrix(), _LABELS)

    # Per-case
    case_rows = [
        [
            r["id"],
            r.get("expected", "—"),
            r.get("got", "ERROR"),
            "✓" if r.get("correct") else "✗",
            r.get("latency_s", "—"),
        ]
        for r in case_results
    ]
    print_table(
        ["ID", "Expected", "Got", "OK?", "Latency(s)"],
        case_rows,
        title="Per-case results",
    )

    results = {
        "benchmark": "intent_classification",
        "provider": cfg["llm"]["provider"],
        "model": cfg["llm"]["model"],
        "total_cases": len(cases),
        "global": {
            "accuracy": round(metrics.accuracy, 4),
            "macro_f1": round(metrics.macro_f1(), 4),
            "weighted_f1": round(metrics.weighted_f1(), 4),
            "errors": metrics.errors,
        },
        "by_class": {
            label: {
                "precision": round(pc[label].precision, 4),
                "recall": round(pc[label].recall, 4),
                "f1": round(pc[label].f1, 4),
                "support": pc[label].support,
            }
            for label in _LABELS
        },
        "confusion_matrix": metrics.confusion_matrix(),
        "cases": case_results,
    }
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Intent classification benchmark")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dataset = args.dataset or resolve_path("datasets/intent_classification.json")
    results = run(cfg, dataset, verbose=args.verbose)

    if args.save:
        results_dir = resolve_path(cfg.get("results_dir", "results"))
        path = save_json(results, "intent_classification", results_dir)
        print(f"\n  Saved to: {path}")
