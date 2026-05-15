# Stage 1: Invoice Collect

## Identity

Collects and normalizes raw invoices from any source. Converts varied formats (PDF, PNG, JPG, email .eml) into a standardized JSONL stream. Passes directly to Stage 2 — this stage has no judge.

---

## Inputs

| Source | Location | What to look for |
|--------|----------|------------------|
| Invoice files | `input/invoices/` | PDF, PNG, JPG, WEBP, EML files |
| Watch queue | (if `--watch` mode) | New files arriving |

---

## Process

1. Scan `input/invoices/` for files matching: `*.pdf`, `*.png`, `*.jpg`, `*.jpeg`, `*.webp`, `*.eml`
2. For each file:
   a. Generate a UUID for the invoice
   b. Copy file to `input/processed/<uuid>.<ext>`
   c. Extract text:
      - PDF → `pdftotext` or `pymupdf`
      - Image → `tesseract` OCR
      - EML → parse email body + attachments
   d. Normalize to JSON:
      ```json
      {
        "invoice_id": "uuid",
        "source_file": "original filename",
        "file_type": "pdf|image|email",
        "collected_at": "ISO8601",
        "raw_text": "... extracted text ...",
        "file_path": "input/processed/<uuid>.<ext>"
      }
      ```
3. Write output to `output/stage1.jsonl` (one JSON object per line)
4. Log to `output/audit.jsonl`

---

## Outputs

| Artifact | Location | Format |
|----------|---------|--------|
| stage1.jsonl | `output/` | JSONL — one invoice per line |
| processed files | `input/processed/` | Original files moved here |
| audit | `output/audit.jsonl` | Append-only decision log |

---

## Audit Checklist

- [ ] All invoice files in `input/invoices/` were processed
- [ ] No files were lost or skipped (check file count)
- [ ] Each invoice has a unique UUID
- [ ] All extracted text is non-empty (at minimum, the raw text field is populated)
- [ ] Files moved to `input/processed/` after extraction (not deleted)
- [ ] Output written to `output/stage1.jsonl`