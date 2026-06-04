"""
Main entry point for the evaluation suite.

Usage:
  python run_eval.py --benchmark all           # run all benchmarks
  python run_eval.py --benchmark extraction    # slot extraction only
  python run_eval.py --benchmark intent        # intent classification only
  python run_eval.py --benchmark task_mode     # task mode only
  python run_eval.py --benchmark quiz          # quiz evaluation only
  python run_eval.py --benchmark simulation    # end-to-end simulation only

Options:
  --config PATH    alternative path to config.yaml
  --verbose / -v   show per-case detail
  --save           save results under results/
  --dataset PATH   override the dataset path (single benchmark only)
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.path_setup import load_config, resolve_path
from core.report import print_section, save_json

BENCHMARKS = {
    "extraction": ("benchmarks.bench_extraction", "datasets/slot_extraction.json"),
    "intent": ("benchmarks.bench_intent", "datasets/intent_classification.json"),
    "task_mode": ("benchmarks.bench_task_mode", "datasets/task_mode.json"),
    "quiz": ("benchmarks.bench_quiz", "datasets/quiz_evaluation.json"),
    "simulation": ("benchmarks.bench_simulation", "datasets/dialog_scenarios.json"),
}


def run_benchmark(
    name: str, cfg: dict, dataset: str | None, verbose: bool, save: bool
) -> dict | None:
    import importlib

    mod_path, default_ds = BENCHMARKS[name]
    try:
        mod = importlib.import_module(mod_path)
    except ImportError as exc:
        print(f"  ERROR importing {mod_path}: {exc}")
        return None

    ds_path = dataset or resolve_path(default_ds)
    if not os.path.isfile(ds_path):
        print(f"  Dataset not found: {ds_path}")
        print(f"  Create or complete the file and run again.")
        return None

    t0 = time.monotonic()
    results = mod.run(cfg, ds_path, verbose=verbose)
    elapsed = time.monotonic() - t0
    print(f"\n  Total benchmark time '{name}': {elapsed:.1f}s")

    if save and results:
        results_dir = resolve_path(cfg.get("results_dir", "results"))
        provider_tag = cfg.get("llm", {}).get("provider", "unknown")
        path = save_json(results, f"{name}_{provider_tag}", results_dir)
        print(f"  Saved to: {path}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Statistical evaluation of the dialog system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--benchmark",
        "-b",
        choices=list(BENCHMARKS.keys()) + ["all"],
        default="all",
        help="Benchmark to run (default: all)",
    )
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument(
        "--dataset", default=None, help="Alternative dataset (single benchmark only)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Per-case detail")
    parser.add_argument("--save", action="store_true", help="Save results as JSON")
    parser.add_argument("--provider", default=None, help="Override LLM provider: gemini | ollama")
    parser.add_argument(
        "--model", default=None, help="Override LLM model (e.g. qwen2.5, gemini-2.5-flash)"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.provider:
        cfg.setdefault("llm", {})["provider"] = args.provider
    if args.model:
        cfg.setdefault("llm", {})["model"] = args.model

    provider = cfg.get("llm", {}).get("provider", "?")
    model = cfg.get("llm", {}).get("model", "?")

    print_section(f"DIALOG SYSTEM EVALUATION  [{provider} / {model}]", width=70)

    if args.benchmark == "all":
        if args.dataset:
            print("  NOTE: --dataset is ignored when benchmark=all")
        all_results = {}
        t_total = time.monotonic()
        for name in BENCHMARKS:
            print(f"\n{'─'*70}")
            print(f"  ▶ {name.upper()}")
            print(f"{'─'*70}")
            res = run_benchmark(name, cfg, None, args.verbose, args.save)
            if res:
                all_results[name] = res.get("global", {})

        elapsed_total = time.monotonic() - t_total
        print_section("EXECUTIVE SUMMARY", width=70)
        for name, g in all_results.items():
            print(f"\n  {name.upper()}")
            for k, v in g.items():
                if v is not None:
                    print(f"    {k:<30} {v}")
        print(f"\n  Total time: {elapsed_total:.1f}s")

    else:
        run_benchmark(args.benchmark, cfg, args.dataset, args.verbose, args.save)


if __name__ == "__main__":
    main()
