# Stage 4: Journal Generation + Judge

## Identity

Reads categorized invoices from Stage 3. Generates double-entry journal entries (debit/credit). Every journal entry is self-consistent: debits equal credits. Runs the judge to verify entry accuracy before export.

---

## Inputs

| Source | Location | Section/Scope |
|--------|----------|---------------|
| Prior stage | `../03-categorize/output/` | `categorized.jsonl` (PROCEED + MISC invoices) |
| Rules | `../../_config/rules/chart_of_accounts.json` | Account codes and names |
| Business config | `../../_config/business_info.json` | Business name, fiscal year start |

---

## Process

### Step 1 — Journal Entry Prompt

```
You are a journal entry generator. Convert invoices into double-entry journal entries.

RULES:
- Every transaction has at least one DEBIT and one CREDIT
- Total debits MUST equal total credits
- For expenses (vendor paid): DEBIT the expense account, CREDIT cash/bank
- For income (customer paid): DEBIT cash/bank, CREDIT the income account
- For credits (negative amount): reverse the logic above

CHART OF ACCOUNTS:
{chart_of_accounts.json}

BUSINESS INFO:
{business_info.json}

For each invoice, generate journal entries:

SCHEMA:
{
  "invoice_id": "uuid",
  "journal_entries": [
    {
      "date": "YYYY-MM-DD",
      "account_name": "string",
      "account_code": "string",
      "entry_type": "DEBIT|CREDIT",
      "amount": "float (positive)",
      "memo": "string (brief description)"
    }
  ],
  "transaction_total": "float",
  "is_balanced": "boolean",
  "entry_count": "int",
  "confidence_notes": "string"
}

EXAMPLE — Expense invoice ($150 Amazon Web Services):
[
  { account: "Software/SaaS", code: "6300", type: "DEBIT", amount: 150.00, memo: "AWS monthly" },
  { account: "Cash/Bank", code: "1000", type: "CREDIT", amount: 150.00, memo: "AWS monthly" }
]

EXAMPLE — Income (credit to account, negative amount -$500):
[
  { account: "Cash/Bank", code: "1000", type: "DEBIT", amount: 500.00, memo: "Payment received" },
  { account: "Sales", code: "4000", type: "CREDIT", amount: 500.00, memo: "Invoice #123" }
]
```

### Step 2 — Judge

```
You are the confidence gate for journal entries. Score 0-1:

1. BALANCE_ACCURACY: Are debits equal to credits?
   - 1.0 = Perfectly balanced (total debits = total credits to the cent)
   - 0.8 = Balanced within rounding (0.01 or less difference)
   - 0.4 = Off by more than 0.01 (incorrect)
   - 0.1 = Clearly unbalanced

2. ENTRY_CORRECTNESS: Are the correct accounts debited/credited?
   - 1.0 = Correct accounts for the transaction type
   - 0.7 = Plausible but unusual account choice
   - 0.4 = Wrong entry type (debit vs credit reversed)
   - 0.1 = Completely wrong accounts

3. MEMO_QUALITY: Are the memos clear and accurate?
   - 1.0 = Clear, accurate, matches invoice
   - 0.7 = Mostly clear
   - 0.4 = Vague or missing
   - 0.1 = Incorrect memo

OVERALL = 0.5*BALANCE + 0.3*ENTRY + 0.2*MEMO

DECISION RULES:
- overall >= 0.85 AND is_balanced == true → PROCEED
- overall >= 0.60 AND < 0.85 → CLARIFY (binary: which account? correct entry type?)
- overall >= 0.40 AND < 0.60 → MISC (set entries to Miscellaneous for both sides)
- overall < 0.40 OR is_balanced == false → FLAG
```

### Step 3 — Route

Same four-way route: PROCEED / CLARIFY / MISC / FLAG.

---

## Outputs

| Artifact | Location | Format |
|----------|---------|--------|
| journal.jsonl | `output/` | JSONL — journal entries per invoice |
| pending_clarifications.jsonl | `output/` | Binary questions |
| flags/ | `output/` | MISC + FLAG artifacts |
| audit.jsonl | `output/` | Decision log |

---

## Audit Checklist

- [ ] Every entry is balanced (debits = credits)
- [ ] Every invoice has at least one journal entry
- [ ] All amounts are positive floats
- [ ] MISC entries used "Miscellaneous" account on both sides
- [ ] CLARIFY questions are binary and actionable
- [ ] Dates from invoices are preserved in journal entries