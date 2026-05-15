# Stage 5: Export + Validate

## Identity

Final validation pass. Reads all journal entries from Stage 4, runs balance checks, generates export files (CSV for spreadsheet import, JSON for API/software import), and produces a summary report.

**No judge — this stage validates mechanically**, not via LLM. If balance checks pass and format checks pass → PASS. If they fail → FAIL with specific error.

---

## Inputs

| Source | Location | Section/Scope |
|--------|----------|---------------|
| Prior stage | `../04-journal/output/` | `journal.jsonl` |
| Business config | `../../_config/business_info.json` | Business name, fiscal year |

---

## Process

### Step 1 — Load journal entries

Read all entries from `journal.jsonl`. Group by invoice_id.

### Step 2 — Mechanical validation

For every journal entry in the file:

```
1. BALANCE CHECK: Sum of DEBIT amounts == Sum of CREDIT amounts (within 0.01)
   → If ANY entry fails: FAIL with invoice_id + actual sums

2. FORMAT CHECK: All required fields present
   → date: YYYY-MM-DD format
   → account_name: non-empty string
   → account_code: 4-digit string
   → entry_type: DEBIT or CREDIT (uppercase)
   → amount: positive float > 0
   → invoice_id: valid UUID
   → If ANY field fails: FAIL with field name + invoice_id

3. COMPLETENESS CHECK: All invoices from prior stages reached Stage 5
   → Count entries in journal.jsonl vs. categorized.jsonl
   → If mismatch: list missing invoice_ids as warnings
```

### Step 3 — Generate exports

**CSV export** (`output/journal_export.csv`):
```csv
date,account_name,account_code,entry_type,amount,memo,invoice_id
2026-05-14,Software/SaaS,6300,DEBIT,150.00,AWS monthly,uuid-here
2026-05-14,Cash/Bank,1000,CREDIT,150.00,AWS monthly,uuid-here
```

**JSON export** (`output/journal_export.json`):
```json
{
  "business_name": "...",
  "exported_at": "ISO8601",
  "fiscal_year": 2026,
  "entries": [...],
  "summary": {
    "total_debits": 0.00,
    "total_credits": 0.00,
    "entry_count": 0,
    "invoice_count": 0,
    "misc_count": 0,
    "flagged_count": 0
  }
}
```

**Summary report** (`output/export_summary.txt`):
```
ICM Bookkeeping — Export Summary
Generated: 2026-05-14T05:00:00Z
─────────────────────────────────
Total journal entries: 24
Total invoices:       12
Total debits:         $4,832.50
Total credits:        $4,832.50
Balanced:             YES

Invoices by status:
  PROCEED:  10  (exported)
  MISC:     1   (flagged — review manually)
  FLAG:      1   (blocked — needs human review)

Export files:
  journal_export.csv  — spreadsheet import
  journal_export.json — API/software import
```

### Step 4 — Flag handling

After export:
- Copy `flags/` from prior stages into `output/flags_review/` with this stage's timestamp
- Write `output/flags_review/README.md` listing all items needing review

---

## Outputs

| Artifact | Location | Format |
|----------|---------|--------|
| journal_export.csv | `output/` | CSV — for spreadsheet import |
| journal_export.json | `output/` | JSON — for API/software import |
| export_summary.txt | `output/` | Human-readable summary |
| flags_review/ | `output/` | All flagged items consolidated |
| audit.jsonl | `output/` | Final decision log |

---

## Audit Checklist

- [ ] All journal entries in journal.jsonl are balanced (mechanical check)
- [ ] All required fields present and correctly formatted
- [ ] CSV has correct headers, one entry per line
- [ ] JSON export is valid JSON
- [ ] Summary totals match (debits = credits)
- [ ] All flagged invoices have a corresponding entry in flags_review/
- [ ] No data was lost between stages (invoice count reconciliation)