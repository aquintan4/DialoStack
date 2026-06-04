"""
Benchmark: slot extraction (NLU gathering phase).

Measures how many slots and values the system extracts correctly given the
user utterance and the current frame state.

Metrics:
  - Global precision / recall / F1
  - Breakdown by slot type (str, int, float, bool, list_str)
  - Per case: correct / incorrect / llm_error / false_positive
"""

import json
import os
import sys
import time

# Path setup must be first
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.path_setup import setup_path, load_config, load_prompts, resolve_path

setup_path()

from core.llm_adapter import make_infer_fn
from core.metrics import BinaryMetrics, values_match, list_overlap
from core.report import print_section, print_table, print_summary, save_json, save_csv

from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.prompt_builder import PromptBuilder
from ros2_dialog_manager.dialog_frame import DialogFrame
from ros2_dialog_manager.dialog_context import DialogContext


def _build_frame(slot_schema: dict, frame_filled: dict) -> DialogFrame:
    frame = DialogFrame.from_slots_json(json.dumps(slot_schema))
    if frame_filled:
        frame.try_update(frame_filled)
    return frame


def _normalize_value(value, slot_type: str):
    if slot_type == "list_str":
        if isinstance(value, list):
            return [str(v).lower().strip() for v in value]
        return [str(value).lower().strip()]
    if isinstance(value, bool):
        return value
    if slot_type == "int":
        return int(value)
    if slot_type == "float":
        return float(value)
    return str(value).lower().strip()


def _extractions_as_dict(extractions: list[dict]) -> dict[str, object]:
    """Convert extraction list to {slot: value} dict for easier comparison."""
    result: dict = {}
    for e in extractions:
        slot = e.get("slot")
        value = e.get("value")
        if slot is not None and value is not None:
            result[slot] = value
    return result


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

    # Global metrics
    global_m = BinaryMetrics()

    # Per slot-type metrics
    type_metrics: dict[str, BinaryMetrics] = {}

    case_results = []

    print_section("BENCHMARK: Slot extraction")
    print(f"  Dataset : {os.path.basename(dataset_path)}")
    print(f"  Cases   : {len(cases)}")
    print(f"  Provider: {cfg['llm']['provider']} / {cfg['llm']['model']}\n")

    total = len(cases)
    for idx, case in enumerate(cases, 1):
        cid = case["id"]
        user_text = case["user_text"]
        expected = case.get("expected_extractions", [])
        slot_schema = case["slot_schema"]
        frame_filled = case.get("frame_filled", {})

        print(f"  [{idx}/{total}] {cid} ...", end="", flush=True)
        if verbose:
            print(f"\n         {case['description']}")
            print(f"         user: '{user_text}'")

        # ==== Build frame and run extraction ====
        try:
            frame = _build_frame(slot_schema, frame_filled)
        except Exception as exc:
            print(f"  [{cid}] ERROR building frame: {exc}")
            global_m.errors += 1
            case_results.append({"id": cid, "status": "frame_error", "error": str(exc)})
            continue

        t0 = time.monotonic()
        try:
            extractions = llm.extract_slots(user_text, frame, ctx=None)
        except Exception as exc:
            global_m.errors += 1
            case_results.append({"id": cid, "status": "llm_error", "error": str(exc)})
            continue
        elapsed = time.monotonic() - t0

        got_dict = _extractions_as_dict(extractions)
        exp_dict = _extractions_as_dict(expected)

        # Per-case TP/FP/FN
        case_tp, case_fp, case_fn = 0, 0, 0
        case_detail = []

        for slot, exp_val in exp_dict.items():
            slot_type = frame.slot_type(slot)
            t_metrics = type_metrics.setdefault(slot_type, BinaryMetrics())

            if slot_type == "list_str":
                got_list = got_dict.get(slot, [])
                if isinstance(got_list, list):
                    tp, fp, fn = list_overlap(
                        got_list, exp_val if isinstance(exp_val, list) else [exp_val]
                    )
                else:
                    tp, fp, fn = 0, 0, len(exp_val) if isinstance(exp_val, list) else 1
                case_tp += tp
                case_fp += fp
                case_fn += fn
                global_m.tp += tp
                global_m.fp += fp
                global_m.fn += fn
                t_metrics.tp += tp
                t_metrics.fp += fp
                t_metrics.fn += fn
                status = "OK" if fp == 0 and fn == 0 else f"partial(tp={tp},fp={fp},fn={fn})"
            else:
                if slot in got_dict and values_match(got_dict[slot], exp_val, slot_type):
                    case_tp += 1
                    global_m.tp += 1
                    t_metrics.tp += 1
                    status = "OK"
                else:
                    case_fn += 1
                    global_m.fn += 1
                    t_metrics.fn += 1
                    status = f"MISS (got {got_dict.get(slot, '—')})"
            case_detail.append(
                {"slot": slot, "expected": exp_val, "got": got_dict.get(slot), "status": status}
            )

        # False positives: extractions not in expected
        for slot in got_dict:
            if slot not in exp_dict:
                case_fp += 1
                global_m.fp += 1
                slot_type = frame.slot_type(slot)
                type_metrics.setdefault(slot_type, BinaryMetrics()).fp += 1
                case_detail.append(
                    {"slot": slot, "expected": None, "got": got_dict[slot], "status": "FP"}
                )

        outcome = "OK" if case_fn == 0 and case_fp == 0 else "PARTIAL" if case_tp > 0 else "MISS"
        case_results.append(
            {
                "id": cid,
                "description": case["description"],
                "user_text": user_text,
                "status": outcome,
                "tp": case_tp,
                "fp": case_fp,
                "fn": case_fn,
                "latency_s": round(elapsed, 3),
                "detail": case_detail,
            }
        )

        print(f" {outcome}  ({elapsed:.2f}s)", flush=True)
        if verbose:
            print(f"         extracted: {got_dict}")
            print(f"         expected : {exp_dict}")

    # ==== Summary ====
    print_section("GLOBAL RESULTS")
    print_summary("Total cases", len(cases))
    print_summary("Precision", f"{global_m.precision:.3f}")
    print_summary("Recall", f"{global_m.recall:.3f}")
    print_summary("F1", f"{global_m.f1:.3f}")
    print_summary("LLM errors", global_m.errors)

    # Per-type breakdown
    type_rows = []
    for slot_type, m in sorted(type_metrics.items()):
        type_rows.append(
            [slot_type, m.support, f"{m.precision:.3f}", f"{m.recall:.3f}", f"{m.f1:.3f}"]
        )
    if type_rows:
        print_table(
            ["Slot type", "Support", "Precision", "Recall", "F1"],
            type_rows,
            title="Breakdown by slot type",
        )

    # Per-case table
    case_rows = [
        [r["id"], r["status"], r["tp"], r["fp"], r["fn"], r.get("latency_s", "—")]
        for r in case_results
    ]
    print_table(
        ["ID", "Status", "TP", "FP", "FN", "Latency(s)"],
        case_rows,
        title="Per-case results",
    )

    results = {
        "benchmark": "slot_extraction",
        "provider": cfg["llm"]["provider"],
        "model": cfg["llm"]["model"],
        "total_cases": len(cases),
        "global": {
            "precision": round(global_m.precision, 4),
            "recall": round(global_m.recall, 4),
            "f1": round(global_m.f1, 4),
            "tp": global_m.tp,
            "fp": global_m.fp,
            "fn": global_m.fn,
            "errors": global_m.errors,
        },
        "by_slot_type": {
            t: {
                "precision": round(m.precision, 4),
                "recall": round(m.recall, 4),
                "f1": round(m.f1, 4),
                "support": m.support,
            }
            for t, m in type_metrics.items()
        },
        "cases": case_results,
    }
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Slot extraction benchmark")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dataset = args.dataset or resolve_path("datasets/slot_extraction.json")
    results = run(cfg, dataset, verbose=args.verbose)

    if args.save:
        results_dir = resolve_path(cfg.get("results_dir", "results"))
        path = save_json(results, "slot_extraction", results_dir)
        print(f"\n  Saved to: {path}")
