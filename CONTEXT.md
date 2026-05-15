# CONTEXT.md — icm-bookkeeping Pipeline

**What this pipeline does:** Autonomous invoice-to-journal bookkeeping. Processes PDF/image invoices through 5 stages, with an LLM judge at each stage deciding whether to proceed, ask a binary clarification, default to MISC, or flag for human review.

**The key design:** This is not "run an LLM on your inbox." This is a staged pipeline where each stage has a focused job, a focused output, and a focused self-critique (the judge). The pipeline runs end-to-end autonomously unless blocked by a low-confidence FLAG.

---

## Pipeline Overview

```
Stage 1: COLLECT          Stage 2: EXTRACT         Stage 3: CATEGORIZE
─────────────────         ─────────────────        ──────────────────
Input: raw invoices       Input: stage1.jsonl      Input: stage2.jsonl
Output: normalized       Output: extracted.jsonl  Output: categorized.jsonl
       invoice list      Judge: vendor, amount,   Judge: category match,
                              completeness             anomaly, duplicate
                              confidence               confidence

Stage 4: JOURNAL          Stage 5: EXPORT
─────────────────        ─────────────────
Input: stage3.jsonl      Input: stage4.jsonl
Output: journal.jsonl  Output: journal.csv
Judge: entry accuracy,  Final: balance check,
       double-entry          format validation,
       consistency           export ready
```

---

## Entry Point

Drop invoices (PDF, PNG, JPG, email .eml) into `input/invoices/`. Run `python scripts/run_pipeline.py --workspace /path/to/workspace --watch` for auto-trigger, or trigger manually.

---

## Judge Decision Reference

| Score | Decision | What happens |
|-------|----------|-------------|
| ≥ 0.85 | **PROCEED** | Next stage immediately |
| 0.60–0.84 | **CLARIFY** | Ask binary question → write rule → retry (max 2×) |
| 0.40–0.59 | **MISC** | Set vendor/category to Miscellaneous, mark flagged, proceed |
| < 0.40 | **FLAG** | Block. Write to `output/flags/`. Await human. |

---

## Rules Live in `_config/rules/`

**These are your learned facts.** Read them before every stage. Write to them after every clarification.

```
_config/rules/
├── vendor_map.csv       ← alias → canonical vendor name
├── category_hints.json ← text patterns → account code
├── amount_ranges.json  ← vendor → {min, max, typical}
└── ignored.json        ← vendor/amount patterns to ignore or MISC
```

---

## Audit Trail

Every stage appends to `output/audit.jsonl`. Each entry:
```json
{
  "ts": "ISO8601",
  "stage": "02-extract",
  "invoice_id": "uuid",
  "judge_score": 0.72,
  "decision": "CLARIFY",
  "reason": "vendor_res 0.5, amount_acc 0.8, completeness 0.85",
  "clarification_question": "Is this 'Amazon' or 'Amazon Web Services'? [Amazon] [AWS]",
  "retry_count": 0
}
```

---

## Pipeline Invocation

```bash
python scripts/run_pipeline.py \
  --workspace /path/to/client-workspace \
  --stages 01-collect,02-extract,03-categorize,04-journal,05-export
```

Add `--watch` to watch the input directory. Add `--verbose` for stage-by-stage output.

---

## Key Principles

1. **Stages are isolation boundaries.** Each stage should be able to fail, retry, and succeed without cascading.
2. **The judge is your self-critique, not a second agent.** It evaluates your own output. Be honest about low confidence.
3. **Rules accumulate.** Each clarification makes the next invoice easier. The first invoice from a vendor is the hardest.
4. **MISC is not failure.** Defaulting to Miscellaneous is the correct behavior when uncertain. Flagged items can be resolved later.
5. **Never guess.** If you don't know, MISC or FLAG. Never fabricate a vendor name or category.