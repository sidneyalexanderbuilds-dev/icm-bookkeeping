# icm-bookkeeping

**Multi-gate LLM-validated bookkeeping pipeline.** Fully agent-driven invoice-to-journal workflow with learned rule sets.

---

## What it does

Parses invoices, extracts and categorizes transactions, and generates double-entry journal entries — autonomously. Humans enter the loop only at confidence breakpoints via binary clarification questions. Over time, the system learns client-specific rules from those answers.

---

## Architecture

```
Invoice → Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5
         Collect   Extract  Categorize Journal  Export
            ↓         ↓         ↓         ↓        ↓
         [file]  [LLM judge] [LLM judge] [LLM judge] [validate]
            │         │         │         │        │
            ▼         ▼         ▼         ▼        ▼
         Normalize Proceed/    Proceed/  Proceed/  CSV/JSON
                    Clarify/  Clarify/  Clarify/  output
                    MISC/     MISC/     MISC/
                    FLAG      FLAG      FLAG
```

Each stage has a judge sub-loop. If confidence is low, the system either:
1. **Clarify** — asks the client a binary question, stores the answer as a rule, retries
2. **MISC** — defaults to Miscellaneous (income or expense), continues pipeline
3. **Flag** — blocks and requests human review

---

## Stages

| # | Stage | What happens | Judge decision |
|---|-------|-------------|----------------|
| 1 | **Collect** | Watch folder, ingest emails, receive uploads. Normalize to `stage1.jsonl` | — (pass-through) |
| 2 | **Extract** | LLM extracts vendor, amount, date, line items, invoice number | PROCEED / CLARIFY / MISC / FLAG |
| 3 | **Categorize** | LLM maps to chart of accounts. Detects duplicates, flags anomalies | PROCEED / CLARIFY / MISC / FLAG |
| 4 | **Journal** | LLM generates double-entry journal entries | PROCEED / CLARIFY / MISC / FLAG |
| 5 | **Export** | Final validation. Output CSV/JSON for accounting software import | PASS / FAIL |

---

## Rule Learning

Rule sets live in `_config/rules/`. They grow from clarifications.

```
_config/rules/
├── vendor_map.csv       # vendor aliases → canonical name
├── category_hints.json  # text patterns → account category
├── amount_ranges.json   # vendor → {min, max, typical}
└── ignored.json        # patterns to skip or MISC-default
```

When a client answers a binary clarification, the system infers a rule from the answer and writes it to the appropriate file. Next invoice from the same vendor uses the learned rule → higher confidence pass-through.

---

## Running the Pipeline

### Prerequisites

- Python 3.10+
- `llama-cli` (llama.cpp) or OpenAI-compatible endpoint
- `scripts/run_pipeline.py` (Python)

### Run all stages

```bash
cd /path/to/icm-bookkeeping
python scripts/run_pipeline.py \
  --workspace /path/to/client-workspace \
  --stages 01-collect,02-extract,03-categorize,04-journal,05-export
```

### Run single stage with review

```bash
python scripts/run_pipeline.py \
  --workspace /path/to/client-workspace \
  --stages 02-extract \
  --review
```

### Watch mode (auto-run on new invoice)

```bash
python scripts/run_pipeline.py \
  --workspace /path/to/client-workspace \
  --watch --watch-dir ./input/invoices
```

---

## Configuration

### Per-client workspace

Scaffold a client workspace from the template:

```bash
python scripts/scaffold.py \
  --template /tmp/icm-bookkeeping \
  --workspace ~/.hermes/workspaces/bookkeeping-acme \
  --client "ACME Corp"
```

This creates a workspace with client-specific rules, chart of accounts, and input/output directories.

### Chart of accounts

Edit `_config/rules/chart_of_accounts.json` to define your chart of accounts:

```json
{
  "expenses": {
    "Office Supplies": "6200",
    "Software/SaaS": "6300",
    "Meals & Entertainment": "6400",
    "Travel": "6500",
    "Professional Services": "6600",
    "Utilities": "6700",
    "Rent": "6800",
    "Miscellaneous": "6900"
  },
  "income": {
    "Sales": "4000",
    "Service Revenue": "4100",
    "Other Income": "4900",
    "Miscellaneous": "4910"
  }
}
```

---

## Multi-Gate Judge System

The judge is an LLM call after each stage. It scores confidence (0-1) on every extracted field and decision, then routes:

| Confidence | Action |
|------------|--------|
| ≥ 0.85 | PROCEED — high confidence, next stage |
| 0.60–0.84 | CLARIFY — binary question to client → rule → retry |
| 0.40–0.59 | DEFAULT_MISC — set to Miscellaneous, continue pipeline, flag for review |
| < 0.40 | FLAG — block, request human review |

After 2 failed retries on the same invoice at the same stage → FLAG for human.

---

## Business Model

- **Free repo:** The pipeline. Run it on your own invoices.
- **Paid early access:**
  - Multi-entity support (multiple businesses, consolidated reporting)
  - Bank statement auto-matching
  - Tax category optimization per jurisdiction
  - SaaS API for accounting software sync (QuickBooks, Xero)
  - Priority rule inferencing and custom model fine-tuning

---

## Citation

If this workflow saves you time, cite it:

> Moy, A. & Sidney Alexander. "icm-bookkeeping: Multi-Gate LLM-Validated Bookkeeping Pipeline." GitHub, 2026. https://github.com/sidneyalexanderbuilds-dev/icm-bookkeeping

---

*Built with ICM (Interpretable Context Methodology) — folder structure as agent architecture.*