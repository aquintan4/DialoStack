"""
Benchmark: end-to-end simulation of complete dialogs.

Runs the real DialogFSM with a simulated user (ScriptedUserAudioIO).
No ROS — production components are instantiated directly.

Per-scenario metrics:
  - success / failure
  - turns_total / turns_expected_min
  - frame_accuracy (correct vs expected slots)
  - failure_reason (if it fails)

Global metrics:
  - Task completion rate (%)
  - Avg turns to completion (successful scenarios only)
  - Avg turns (all)
  - Mean frame accuracy
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.path_setup import setup_path, load_config, load_prompts, resolve_path

setup_path()

from core.llm_adapter import make_infer_fn
from core.mock_audio import ScriptedUserAudioIO
from core.metrics import values_match
from core.report import print_section, print_table, print_summary, save_json

from ros2_dialog_manager.llm_client import LLMDialogClient
from ros2_dialog_manager.prompt_builder import PromptBuilder
from ros2_dialog_manager.dialog_context import DialogContext, Resource
from ros2_dialog_manager.dialog_fsm import DialogFSM
from ros2_dialog_manager.strategies import FSMConfig, build_strategy


class _MockRequest:
    """Minimal request object that mimics the ROS DialogTask goal."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _frame_accuracy(final_frame: dict, expected_frame: dict) -> float:
    """Fraction of expected slots that match in the final frame."""
    if not expected_frame:
        return 1.0
    correct = 0
    for slot, exp_val in expected_frame.items():
        got_val = final_frame.get(slot)
        if got_val is None:
            continue
        if isinstance(exp_val, list):
            got_set = {
                str(v).lower().strip()
                for v in (got_val if isinstance(got_val, list) else [got_val])
            }
            exp_set = {str(v).lower().strip() for v in exp_val}
            if got_set == exp_set:
                correct += 1
        else:
            if str(got_val).lower().strip() == str(exp_val).lower().strip():
                correct += 1
    return correct / len(expected_frame)


def _build_context(scenario: dict) -> DialogContext:
    resources = []
    resources_raw = scenario.get("resources_json", "[]")
    if resources_raw:
        try:
            for r in json.loads(resources_raw):
                if isinstance(r, dict) and "name" in r and "content" in r:
                    resources.append(
                        Resource(
                            name=r["name"],
                            description=r.get("description", ""),
                            content=r["content"],
                        )
                    )
        except Exception:
            pass
    return DialogContext(resources=resources, domain=scenario.get("domain", ""))


def run(cfg: dict, dataset_path: str, verbose: bool = False) -> dict:
    prompts_path = resolve_path(cfg["prompts_yaml"])
    templates = load_prompts(prompts_path)
    language = cfg.get("dialog", {}).get("language", "Spanish")
    history_max = cfg.get("dialog", {}).get("history_max_turns", 200)
    max_turns = cfg.get("dialog", {}).get("max_turns_simulation", 20)

    infer_fn = make_infer_fn(cfg)
    pb = PromptBuilder(templates, language=language)

    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)
    cases = dataset.get("cases", [])

    print_section("BENCHMARK: End-to-end dialog simulation")
    print(f"  Dataset  : {os.path.basename(dataset_path)}")
    print(f"  Scenarios: {len(cases)}")
    print(f"  Provider : {cfg['llm']['provider']} / {cfg['llm']['model']}")
    print(f"  Max turns: {max_turns}\n")

    case_results = []
    success_turns = []
    all_turns = []
    frame_accuracies = []

    total_cases = len(cases)
    for idx, scenario in enumerate(cases, 1):
        sid = scenario["id"]
        task = scenario["task_description"]
        dialog_mode = scenario.get("dialog_mode", "slot_filling")
        expected_success = bool(scenario.get("expected_success", True))
        expected_frame = scenario.get("expected_final_frame", {})
        user_script = scenario.get("user_script", [])

        print(f"  [{idx}/{total_cases}] {sid}  {scenario['description']}", flush=True)
        if verbose:
            print(f"         task   : {task}")
            print(f"         mode   : {dialog_mode}")
            print(f"         script : {user_script}")

        llm = LLMDialogClient(
            nlu_session_id=f"{sid}_nlu",
            nlg_session_id=f"{sid}_nlg",
            infer_fn=infer_fn,
            prompt_builder=pb,
            language=language,
            history_max_turns=history_max,
        )

        config = FSMConfig(
            max_turns=max_turns,
            max_timeouts=2,
            max_unclear=3,
            max_attempts=3,
            ack_phrases=("Anotado.", "Entendido.", "Perfecto."),
        )

        ctx = _build_context(scenario)

        request = _MockRequest(
            task_description=task,
            dialog_mode=dialog_mode,
            frame_schema_json=scenario.get("frame_schema_json", ""),
            initial_frame_json="",
            resources_json=scenario.get("resources_json", "[]"),
            domain=scenario.get("domain", ""),
            max_turns=max_turns,
        )

        try:
            strategy = build_strategy(
                mode=dialog_mode,
                llm=llm,
                config=config,
                ctx=ctx,
                request=request,
            )
        except Exception as exc:
            print(f"         ERROR building strategy: {exc}")
            case_results.append({"id": sid, "status": "strategy_error", "error": str(exc)})
            continue

        audio = ScriptedUserAudioIO(user_script, verbose=verbose)

        feedback_log = []

        fsm = DialogFSM(
            task=task,
            strategy=strategy,
            audio=audio,
            config=config,
            on_feedback=lambda phase, frame_json, utterance, turns: feedback_log.append(
                {"phase": phase, "turns": turns, "utterance": utterance[:80]}
            ),
            is_cancelled=lambda: False,
            timeout_prompt="¿Sigues ahí?",
            log_path=None,
        )

        t0 = time.monotonic()
        try:
            result = fsm.run()
        except Exception as exc:
            elapsed = time.monotonic() - t0
            print(f"         ERROR in FSM: {exc}")
            case_results.append(
                {
                    "id": sid,
                    "status": "fsm_error",
                    "error": str(exc),
                    "elapsed_s": round(elapsed, 2),
                }
            )
            continue
        elapsed = time.monotonic() - t0

        final_frame = result.final_json
        try:
            final_frame_dict = json.loads(final_frame)
        except Exception:
            final_frame_dict = {}

        fa = _frame_accuracy(final_frame_dict, expected_frame) if expected_frame else None
        if fa is not None:
            frame_accuracies.append(fa)

        all_turns.append(result.total_turns)
        if result.success:
            success_turns.append(result.total_turns)

        outcome_ok = result.success == expected_success
        case_r = {
            "id": sid,
            "description": scenario["description"],
            "success": result.success,
            "expected_success": expected_success,
            "outcome_ok": outcome_ok,
            "total_turns": result.total_turns,
            "failure_reason": result.failure_reason,
            "final_frame": final_frame_dict,
            "frame_accuracy": round(fa, 3) if fa is not None else "n/a",
            "elapsed_s": round(elapsed, 2),
        }
        case_results.append(case_r)

        fa_str = f"{fa:.2f}" if fa is not None else "n/a"
        mark = "✓" if outcome_ok else "✗"
        print(
            f"         {'SUCCESS' if result.success else 'FAILURE':7}  turns={result.total_turns}  frame_acc={fa_str}  {mark}  ({elapsed:.1f}s)"
        )
        if not result.success and result.failure_reason:
            print(f"         reason: {result.failure_reason}")
        if verbose:
            print(f"         final frame: {final_frame_dict}")
        print()

    # ==== Global stats ====
    total = len(case_results)
    successful = sum(1 for r in case_results if r.get("success"))
    outcome_ok_count = sum(1 for r in case_results if r.get("outcome_ok"))
    completion_rate = successful / total if total > 0 else 0.0
    avg_turns_success = sum(success_turns) / len(success_turns) if success_turns else 0.0
    avg_turns_all = sum(all_turns) / len(all_turns) if all_turns else 0.0
    avg_fa = sum(frame_accuracies) / len(frame_accuracies) if frame_accuracies else 0.0

    print_section("GLOBAL RESULTS")
    print_summary("Total scenarios", total)
    print_summary("Task completion rate", f"{completion_rate:.1%}")
    print_summary("Correct predictions", f"{outcome_ok_count}/{total}")
    print_summary("Avg turns (success)", f"{avg_turns_success:.1f}")
    print_summary("Avg turns (all)", f"{avg_turns_all:.1f}")
    if frame_accuracies:
        print_summary("Mean frame accuracy", f"{avg_fa:.3f}")

    # Failure reasons
    reasons: dict[str, int] = {}
    for r in case_results:
        reason = r.get("failure_reason") or ""
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    if reasons:
        print_table(
            ["Failure reason", "Occurrences"],
            [[k, v] for k, v in sorted(reasons.items(), key=lambda x: -x[1])],
            title="Failure reasons",
        )

    # Per-case summary
    case_rows = [
        [
            r["id"],
            "✓" if r.get("success") else "✗",
            r.get("total_turns", "—"),
            r.get("frame_accuracy", "n/a"),
            "✓" if r.get("outcome_ok") else "✗",
            r.get("elapsed_s", "—"),
        ]
        for r in case_results
    ]
    print_table(
        ["ID", "Success", "Turns", "Frame acc.", "Pred OK", "Time(s)"],
        case_rows,
        title="Per-scenario summary",
    )

    results = {
        "benchmark": "dialog_simulation",
        "provider": cfg["llm"]["provider"],
        "model": cfg["llm"]["model"],
        "total_scenarios": total,
        "global": {
            "completion_rate": round(completion_rate, 4),
            "avg_turns_success": round(avg_turns_success, 2),
            "avg_turns_all": round(avg_turns_all, 2),
            "avg_frame_accuracy": round(avg_fa, 4) if frame_accuracies else None,
            "outcome_accuracy": round(outcome_ok_count / total, 4) if total > 0 else 0.0,
        },
        "cases": case_results,
    }
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="End-to-end dialog simulation benchmark")
    parser.add_argument("--config", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dataset = args.dataset or resolve_path("datasets/dialog_scenarios.json")
    results = run(cfg, dataset, verbose=args.verbose)

    if args.save:
        results_dir = resolve_path(cfg.get("results_dir", "results"))
        path = save_json(results, "dialog_simulation", results_dir)
        print(f"\n  Saved to: {path}")
