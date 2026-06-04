"""
Benchmark: quiz answer evaluation (evaluate_quiz_answer).

Measures whether the LLM correctly judges if the user answer is right,
comparing against the manually annotated ground_truth_correct.

Metrics:
  - Global accuracy of the LLM evaluator
  - False positive rate (marks an incorrect answer as correct)
  - False negative rate (marks a correct answer as incorrect)
  - Case distribution: correct / incorrect / llm_error
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.path_setup import setup_path, load_config, load_prompts, resolve_path

setup_path()

from core.llm_adapter import make_infer_fn
from core.metrics import BinaryMetrics
from core.report import print_section, print_table, print_summary, save_json

from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.prompt_builder import PromptBuilder


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

    # Accuracy of the LLM evaluator vs ground truth
    # TP: LLM says correct AND ground truth is correct
    # TN: LLM says incorrect AND ground truth is incorrect
    # FP: LLM says correct BUT ground truth is incorrect (dangerous: rewards wrong answers)
    # FN: LLM says incorrect BUT ground truth is correct (penalises right answers)

    tp = tn = fp = fn = errors = 0
    case_results = []
    latencies = []

    print_section("BENCHMARK: Quiz answer evaluation")
    print(f"  Dataset : {os.path.basename(dataset_path)}")
    print(f"  Cases   : {len(cases)}")
    print(f"  Provider: {cfg['llm']['provider']} / {cfg['llm']['model']}\n")

    total_cases = len(cases)
    for idx, case in enumerate(cases, 1):
        cid = case["id"]
        question = case["question"]
        expected_answer = case["expected_answer"]
        given_answer = case["given_answer"]
        ground_truth = bool(case["ground_truth_correct"])

        print(f"  [{idx}/{total_cases}] {cid} ...", end="", flush=True)
        if verbose:
            print(f"\n         {case['description']}")
            print(f"         question: '{question}'")
            print(f"         expected: '{expected_answer}'")
            print(f"         given   : '{given_answer}'")

        t0 = time.monotonic()
        try:
            evaluation = llm.evaluate_quiz_answer(
                question=question,
                expected=expected_answer,
                given=given_answer,
            )
        except Exception as exc:
            errors += 1
            case_results.append({"id": cid, "status": "llm_error", "error": str(exc)})
            if verbose:
                print(f"         ERROR: {exc}\n")
            continue
        elapsed = time.monotonic() - t0
        latencies.append(elapsed)

        llm_says_correct = bool(evaluation.get("correct", False))
        feedback = evaluation.get("feedback", "")

        if llm_says_correct and ground_truth:
            tp += 1
            outcome = "TP"
        elif not llm_says_correct and not ground_truth:
            tn += 1
            outcome = "TN"
        elif llm_says_correct and not ground_truth:
            fp += 1
            outcome = "FP (false positive — dangerous)"
        else:
            fn += 1
            outcome = "FN (false negative)"

        case_results.append(
            {
                "id": cid,
                "description": case["description"],
                "ground_truth": ground_truth,
                "llm_says": llm_says_correct,
                "outcome": outcome.split()[0],
                "feedback": feedback,
                "latency_s": round(elapsed, 3),
            }
        )

        short = outcome.split()[0]
        print(f" {short}  ({elapsed:.2f}s)", flush=True)
        if verbose:
            print(
                f"         LLM: {'correct' if llm_says_correct else 'incorrect'}  |  GT: {'correct' if ground_truth else 'incorrect'}"
            )

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print_section("GLOBAL RESULTS")
    print_summary("Total cases evaluated", total)
    print_summary("LLM evaluator accuracy", f"{accuracy:.3f}")
    print_summary("True positives (TP)", tp)
    print_summary("True negatives (TN)", tn)
    print_summary("False positives (FP) ⚠", fp)
    print_summary("False negatives (FN)", fn)
    print_summary("LLM errors", errors)
    print_summary("Mean latency (s)", f"{avg_latency:.3f}")

    case_rows = [
        [
            r["id"],
            "✓" if r.get("ground_truth") else "✗",
            "✓" if r.get("llm_says") else "✗",
            r.get("outcome", "ERROR"),
            r.get("latency_s", "—"),
        ]
        for r in case_results
    ]
    print_table(
        ["ID", "GT", "LLM", "Outcome", "Latency(s)"],
        case_rows,
        title="Per-case results",
    )

    results = {
        "benchmark": "quiz_evaluation",
        "provider": cfg["llm"]["provider"],
        "model": cfg["llm"]["model"],
        "total_cases": total,
        "global": {
            "accuracy": round(accuracy, 4),
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "errors": errors,
            "avg_latency_s": round(avg_latency, 4),
        },
        "cases": case_results,
    }
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quiz evaluation benchmark")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dataset = args.dataset or resolve_path("datasets/quiz_evaluation.json")
    results = run(cfg, dataset, verbose=args.verbose)

    if args.save:
        results_dir = resolve_path(cfg.get("results_dir", "results"))
        path = save_json(results, "quiz_evaluation", results_dir)
        print(f"\n  Saved to: {path}")
