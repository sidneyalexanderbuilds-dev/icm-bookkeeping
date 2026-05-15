# Stage 3: Categorize + Judge

## Identity

Reads extracted invoices from Stage 2. Maps each to the chart of accounts, detects duplicates and anomalies, and routes via confidence. Learned rules from clarifications are applied first — this stage gets smarter over time.

---

## Inputs

| Source | Location | Section/Scope |
|--------|----------|---------------|
| Prior stage | `../02-extract/output/` | `extracted.jsonl` (PROCEED + MISC invoices) |
| Rules | `../../_config/rules/` | Full rules directory |
| Chart of accounts | `../../_config/rules/chart_of_accounts.json` | All accounts |

---

## Process

### Step 1 — Load rules

Before processing any invoice, load:
- `rules/vendor_map.csv` → build vendor → canonical name + default category map
- `rules/category_hints.json` → text patterns → account code hints
- `rules/amount_ranges.json` → vendor → {min, max, typical}

### Step 2 — Categorization prompt

```
You are an invoice categorization agent. You have the chart of accounts and learned rules.

CHART OF ACCOUNTS:
{rules/chart_of_accounts.json — full content}

LEARNED VENDOR RULES:
{rules/vendor_map.csv — loaded into context}

For each invoice, decide:
1. Is this a duplicate of a recent invoice? (same vendor + amount + date ± 2 days)
2. What category does this belong to?
3. Is the amount within the expected range for this vendor?

Respond with this JSON per invoice:
{
  "invoice_id": "uuid",
  "category": "string (account name, e.g., 'Software/SaaS')",
  "account_code": "string (e.g., '6300')",
  "is_duplicate": "boolean",
  "duplicate_of_invoice_id": "string|null",
  "amount_anomaly": "boolean (true if outside vendor's typical range)",
  "anomaly_note": "string|null",
  "categorization_confidence": "high|medium|low",
  "rule_applied": "string|null (which rule determined this category)"
}

If duplicate: set category from the original invoice.
If anomaly: flag but do NOT block — set anomaly_note.
If no rule matches: use category_hints.json patterns, then fall back to judgment.
```

### Step 3 — Judge

```
You are the confidence gate for invoice categorization. Score confidence 0-1:

1. CATEGORY_APPROPRIATENESS: Is the category correct given the vendor and amount?
   - 1.0 = Rule matches or clear category (Amazon → Software/SaaS, Whole Foods → Meals)
   - 0.8 = Category matches with minor ambiguity
   - 0.6 = Plausible but could be another category
   - 0.4 = Likely wrong (Amazon categorized as Meals is wrong)
   - 0.2 = Clearly wrong

2. DUPLICATE_DETECTION: Is the duplicate flag correct?
   - 1.0 = Confirmed duplicate (exact match vendor+amount+date)
   - 0.7 = Likely duplicate (close match)
   - 0.5 = Unsure (could be same vendor different invoice)
   - 0.3 = Probably not duplicate
   - 0.1 = Clearly not duplicate

3. ANOMALY_CATCH: Is the anomaly detection accurate?
   - 1.0 = Amount outside range, correctly flagged
   - 0.8 = Flagged correctly
   - 0.5 = Amount within range but flagged (false positive)
   - 0.3 = Amount outside range but not flagged (false negative)

OVERALL = 0.4*CATEGORY + 0.3*DUPLICATE + 0.3*ANOMALY

DECISION RULES:
- overall >= 0.85 → PROCEED
- overall >= 0.60 AND < 0.85 → CLARIFY
  - Binary question example: "Is this 'Software/SaaS' or 'Professional Services'? [Software] [ProServ]"
  - Binary question example: "Is this a duplicate of invoice from [date]? [Yes] [No]"
- overall >= 0.40 AND < 0.60 → MISC (set to "Miscellaneous - Expenses" or "Miscellaneous - Income")
- overall < 0.40 → FLAG
```

### Step 4 — Route

Same pattern as Stage 2: PROCEED → next stage, CLARIFY → ask + learn + retry, MISC → default + flag, FLAG → block.

---

## Duplicate Detection Storage

Store processed invoice fingerprints in `output/fingerprint_index.jsonl`:
```json
{"vendor_hash": "sha256", "amount": 0.00, "date": "YYYY-MM-DD", "invoice_id": "uuid"}
```

Use this to detect duplicates across runs (not just within the current batch).

---

## Outputs

| Artifact | Location | Format |
|----------|---------|--------|
| categorized.jsonl | `output/` | JSONL — invoices with category + account code |
| fingerprint_index.jsonl | `output/` | Per-run duplicate index |
| pending_clarifications.jsonl | `output/` | Binary questions for client |
| flags/ | `output/` | MISC + FLAG artifacts |
| audit.jsonl | `output/` | Decision log |

---

## Audit Checklist

- [ ] All Stage 2 PROCEED + MISC invoices processed
- [ ] Duplicate detection ran for every invoice
- [ ] All categories mapped to account codes (no unmapped categories)
- [ ] Anomalies flagged with notes
- [ ] CLARIFY questions are binary
- [ ] Learned rules applied first (vendor rules take precedence over LLM judgment)