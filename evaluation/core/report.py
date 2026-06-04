"""
Report formatting and persistence.

print_table   — ASCII table to stdout.
save_json     — dump results dict to results/<benchmark>_<timestamp>.json.
save_csv      — dump a list of row-dicts to CSV.
print_section — section header for readability.
"""

import csv
import json
import os
from datetime import datetime
from typing import Any


def print_section(title: str, width: int = 60) -> None:
    print(f"\n{'═' * width}")
    print(f"  {title}")
    print(f"{'═' * width}")


def print_table(headers: list[str], rows: list[list[Any]], title: str = "") -> None:
    if title:
        print(f"\n  {title}")
    all_rows = [headers] + [[str(v) for v in r] for r in rows]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    sep = "  " + "  ".join("─" * w for w in widths)
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))
    print()


def print_summary(label: str, value: float | int | str, suffix: str = "") -> None:
    print(f"  {label:<30} {value}{suffix}")


def save_json(results: dict, benchmark_name: str, results_dir: str) -> str:
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{benchmark_name}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return path


def save_csv(rows: list[dict], benchmark_name: str, results_dir: str) -> str:
    if not rows:
        return ""
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{benchmark_name}_{ts}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path
