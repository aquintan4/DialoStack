# DialoStack Evaluation Suite

Statistical benchmarks for the dialog system. They run **without ROS** by importing the production modules directly.

## Structure

```
evaluation/
├── config.yaml          ← configures the LLM provider (Gemini / Ollama)
├── run_eval.py          ← main entry point
├── core/                ← infrastructure (LLM adapter, mock audio, metrics)
├── datasets/            ← evaluation datasets in JSON (hand-annotated)
├── benchmarks/          ← one script per benchmark
└── results/             ← generated JSON and CSV files (not committed)
```

## Requirements

```bash
pip install pyyaml google-genai   # for Gemini (already installed in the environment)
# or: pip install requests         # for Ollama
```

## Configuration

Edit `config.yaml`. The most important field:

```yaml
llm:
  provider: "gemini"          # or "ollama"
  model: "gemini-2.5-flash"
  api_key: ""                 # empty → uses the GEMINI_API_KEY environment variable
```

Make sure `GEMINI_API_KEY` is exported in your terminal before running.

## Running

```bash
cd evaluation

# All benchmarks
python run_eval.py --benchmark all --save

# Slot extraction only (with per-case detail)
python run_eval.py --benchmark extraction --verbose

# End-to-end simulation only, saving the result
python run_eval.py --benchmark simulation --save

# With an alternative dataset
python run_eval.py --benchmark extraction --dataset /path/to/my_dataset.json
```

## The 5 benchmarks

| Benchmark | What it measures | Main metric |
|-----------|------------------|-------------|
| `extraction` | NLU slot extraction | Precision / Recall / F1 |
| `intent` | Intent classification at confirmation | Accuracy + Macro-F1 + Confusion matrix |
| `task_mode` | slot_filling or explanation? | Accuracy |
| `quiz` | Quiz answer evaluation | LLM evaluator accuracy |
| `simulation` | Full end-to-end dialog | Task completion rate + avg turns |

## How to add cases to a dataset

Each dataset has an `_instructions` field that explains exactly how to annotate each entry. Read those instructions before adding cases.

**Golden rule**: you decide the `ground_truth`, not the LLM. You may use an LLM to draft cases, but always review and correct each one manually.

Recommended minimum for statistical rigor:
- `slot_extraction`: ≥ 40 cases (distributed across slot types)
- `intent_classification`: ≥ 15 per class = ≥ 60 total
- `task_mode`: ≥ 20 cases (10 per class)
- `quiz_evaluation`: ≥ 30 cases (distributed across correct/incorrect)
- `dialog_scenarios`: ≥ 15 scenarios (happy path + corrections + abandonments)

## How to interpret the results

- **F1 ≥ 0.90**: excellent, production-ready
- **F1 0.80 to 0.89**: good, acceptable for most deployments
- **F1 < 0.80**: review the prompts or the dataset

FPs in `quiz` are more serious than FNs: they mean the system rewards incorrect answers.

The `confirms` → `unclear` errors in `intent` are costly: the system fails to close the dialog even though the user has confirmed.
