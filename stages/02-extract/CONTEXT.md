# Stage 2: Invoice Extract + Judge

## Identity

Reads normalized invoices from Stage 1. Uses an LLM to extract structured fields: vendor, amount, tax, date, line items, payment terms, invoice number. Then runs the judge to score confidence and route the decision.

---

## Inputs

| Source | Location | Section/Scope |
|--------|----------|---------------|
| Prior stage | `../01-collect/output/` | Full `stage1.jsonl` |
| Rules | `../../_config/rules/` | `vendor_map.csv`, `amount_ranges.json` |

---

## Process

### Step 1 — Extraction

For each invoice in `stage1.jsonl`, call the LLM with this prompt:

```
You are an invoice extraction agent. Extract structured data from the following invoice.

Return a JSON object with these fields:
- vendor: canonical vendor name (use rules/vendor_map.csv for alias resolution)
- amount: total amount (float, USD)
- tax: tax amount (float|null)
- date: invoice date (YYYY-MM-DD)
- line_items: array of {description, qty, unit_price, total}
- payment_terms: string|null (e.g., "Net 30")
- invoice_number: string|null
- raw_text: the original extracted text (unchanged, for audit)
- confidence_notes: string (brief notes on any extraction uncertainty)

SCHEMA:
{
  "vendor": "string",
  "amount": "float",
  "tax": "float|null",
  "date": "YYYY-MM-DD",
  "line_items": [{"description":"string","qty":1,"unit_price":0.00,"total":0.00}],
  "payment_terms": "string|null",
  "invoice_number": "string|null",
  "raw_text": "string",
  "confidence_notes": "string"
}

If any field cannot be determined, use null. Do not guess.
```

### Step 2 — Judge

After extraction, call the judge with:

```
You are the confidence gate for invoice extraction. Score your confidence 0-1 on the extraction you just performed.

Score these three dimensions independently:

1. VENDOR_RESOLUTION: Do you know exactly which vendor this is?
   - 1.0 = Exact match (vendor in ruleset or unambiguous name)
   - 0.8 = High confidence (WHOLEFDS → Whole Foods, AMZN → Amazon)
   - 0.6 = Medium (plausible vendor but unusual pattern)
   - 0.4 = Low (fuzzy match, cannot resolve with certainty)
   - 0.2 = None (cannot identify vendor at all)

2. AMOUNT_ACCURACY: Are the numbers correct?
   - 1.0 = Verified (line items sum to total, tax correct)
   - 0.8 = Consistent (totals plausible, no obvious error)
   - 0.6 = Reasonable (within vendor's typical range per rules/amount_ranges.json)
   - 0.4 = Suspicious (amount outside expected range)
   - 0.2 = Incorrect (obvious mismatch)

3. COMPLETENESS: Are all required fields present?
   - 1.0 = Complete (all fields populated)
   - 0.7 = Mostly complete (vendor/amount/date present, extras null)
   - 0.5 = Partial (some critical fields null)
   - 0.2 = Incomplete (critical fields missing)

OVERALL = min(VENDOR_RESOLUTION, AMOUNT_ACCURACY, COMPLETENESS)

Respond with ONLY this JSON:
{
  "vendor_resolution_score": X,
  "amount_accuracy_score": X,
  "completeness_score": X,
  "overall_confidence": X,
  "decision": "PROCEED|CLARIFY|MISC|FLAG",
  "clarification_question": "string|null",
  "clarification_options": ["A","B"]|null,
  "reason": "string (brief)"
}

DECISION RULES:
- overall >= 0.85 → PROCEED
- overall >= 0.60 AND < 0.85 → CLARIFY
  - Set clarification_question to a binary vendor question
  - Example: "Is this 'Amazon' or 'Amazon Web Services'?" with options ["Amazon","AWS"]
  - Example: "Is this '$150.00' or '$1,500.00'?" with options ["$150.00","$1,500.00"]
- overall >= 0.40 AND < 0.60 → MISC (vendor = "Miscellaneous - Expenses" or "Miscellaneous - Income")
- overall < 0.40 → FLAG
```

### Step 3 — Route

```
IF decision == PROCEED:
    write to output/extracted.jsonl
    continue

IF decision == CLARIFY:
    write clarification to output/pending_clarifications.jsonl
    show binary question to client (via handle_clarification.py)
    AFTER client answers:
        infer rule from answer → write to rules/
        retry extraction with resolved input
        if retry succeeds → PROCEED, write to output/extracted.jsonl
        if retry fails again → MISC (after 2 retries)
    continue

IF decision == MISC:
    vendor = "Miscellaneous - Expenses" (or "Miscellaneous - Income" if credit)
    amount > 0 → Expenses; amount < 0 → Income
    write to output/extracted.jsonl with flag: "misc": true
    write to output/flags/misc_<invoice_id>.json
    continue

IF decision == FLAG:
    write to output/flags/flagged_<invoice_id>.json
    DO NOT proceed to next stage for this invoice
    await human review
```

---

## Outputs

| Artifact | Location | Format |
|----------|---------|--------|
| extracted.jsonl | `output/` | JSONL — each invoice with extracted fields + judge scores |
| pending_clarifications.jsonl | `output/` | Clarifications awaiting client answer |
| flags/misc_\*.json | `output/` | MISC invoices flagged for review |
| flags/flagged_\*.json | `output/` | BLOCKED invoices awaiting human review |
| audit.jsonl | `output/` | Decision log |

---

## Audit Checklist

- [ ] Every invoice from Stage 1 was processed (count match)
- [ ] Each extraction has judge scores in the output
- [ ] CLARIFY invoices have binary questions (not open-ended)
- [ ] MISC invoices are flagged and logged
- [ ] Rules were written after each clarification answer
- [ ] Audit log is append-only