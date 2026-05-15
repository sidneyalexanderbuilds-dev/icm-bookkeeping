#!/usr/bin/env python3
"""
run_pipeline.py — ICM Bookkeeping Pipeline Runner

Usage:
    python run_pipeline.py --workspace /path/to/client-workspace [--watch]
    python run_pipeline.py --workspace /path/to/client-workspace --stages 02-extract --review
    python run_pipeline.py --workspace /path/to/client-workspace --stages 01-collect,02-extract,03-categorize,04-journal,05-export
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

STAGES = ["01-collect", "02-extract", "03-categorize", "04-journal", "05-export"]
LLM_PROVIDER = os.environ.get("ICM_LLM_PROVIDER", "openai")  # openai | anthropic | local
LLM_MODEL = os.environ.get("ICM_LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.environ.get("ICM_LLM_BASE_URL", None)  # for local/custom endpoints

# Confidence thresholds
THRESHOLD_PROCEED = 0.85
THRESHOLD_CLARIFY = 0.60
THRESHOLD_MISC = 0.40
MAX_RETRIES = 2

# ── Helpers ────────────────────────────────────────────────────────────────────


def log(msg, verbose=True):
    if verbose:
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"[{ts}] {msg}")


def load_jsonl(path):
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records, mode="w"):
    with open(path, mode) as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def append_audit(stage_dir, record):
    audit_path = stage_dir / "output" / "audit.jsonl"
    with open(audit_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_llm(system_prompt, user_prompt, temperature=0.0):
    """Call the configured LLM. Replace with your provider's client."""
    if LLM_PROVIDER == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            print("openai package not found. Install: pip install openai")
            sys.exit(1)
        client = OpenAI(base_url=LLM_BASE_URL) if LLM_BASE_URL else OpenAI()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return resp.choices[0].message.content

    elif LLM_PROVIDER == "anthropic":
        try:
            from anthropic import Anthropic
        except ImportError:
            print("anthropic package not found. Install: pip install anthropic")
            sys.exit(1)
        client = Anthropic(base_url=LLM_BASE_URL) if LLM_BASE_URL else Anthropic()
        resp = client.messages.create(
            model=LLM_MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        return resp.content[0].text

    elif LLM_PROVIDER == "local":
        # llama.cpp / Ollama — typical OpenAI-compatible local endpoint
        try:
            import httpx
        except ImportError:
            print("httpx not found. Install: pip install httpx")
            sys.exit(1)
        base = LLM_BASE_URL or "http://localhost:11434/v1"
        resp = httpx.post(
            f"{base}/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


def call_judge(judge_prompt, extraction_result):
    """Call the judge LLM to score confidence."""
    judge_system = "You are the confidence gate. Score confidence 0-1. Return ONLY JSON."
    judge_user = f"Extraction result:\n{json.dumps(extraction_result, indent=2)}\n\nJudge prompt:\n{judge_prompt}"
    raw = run_llm(judge_system, judge_user)
    # Strip markdown code blocks if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().strip("`")
    return json.loads(raw)


# ── Stage Runners ──────────────────────────────────────────────────────────────


def run_stage_collect(workspace, verbose=True):
    """Stage 1: Collect and normalize invoices."""
    stage_dir = workspace / "stages" / "01-collect"
    input_dir = workspace / "input" / "invoices"
    processed_dir = workspace / "input" / "processed"
    output_file = stage_dir / "output" / "stage1.jsonl"

    processed_dir.mkdir(parents=True, exist_ok=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists():
        output_file.unlink()

    # Find invoice files
    extensions = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".eml"]
    files = []
    for ext in extensions:
        files.extend(input_dir.glob(f"*{ext}"))

    if not files:
        log("No invoice files found in input/invoices/", verbose)
        return True

    log(f"Collecting {len(files)} invoice(s)...", verbose)

    for f in files:
        invoice_id = str(uuid.uuid4())
        ext = f.suffix.lower()
        dest = processed_dir / f"{invoice_id}{ext}"

        # Copy file
        import shutil
        shutil.copy2(f, dest)

        # Extract text (placeholder — replace with actual extraction logic)
        raw_text = extract_text(f)

        record = {
            "invoice_id": invoice_id,
            "source_file": f.name,
            "file_type": "pdf" if ext == ".pdf" else ("image" if ext in [".png",".jpg",".jpeg",".webp"] else "email"),
            "collected_at": datetime.now().isoformat(),
            "raw_text": raw_text,
            "file_path": str(dest),
        }
        write_jsonl(output_file, [record])

        # Audit
        append_audit(stage_dir, {
            "ts": datetime.now().isoformat(),
            "stage": "01-collect",
            "invoice_id": invoice_id,
            "action": "collected",
            "file": f.name,
        })

        # Move original to processed
        f.rename(input_dir / "processed" / f.name)

    log(f"Collected {len(files)} invoice(s). Output: {output_file}", verbose)
    return True


def extract_text(file_path):
    """Extract text from invoice file. Replace with actual implementation."""
    ext = file_path.suffix.lower()
    try:
        if ext == ".pdf":
            import subprocess
            result = subprocess.run(
                ["pdftotext", str(file_path), "-"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout
        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            # Use tesseract OCR
            import subprocess
            result = subprocess.run(
                ["tesseract", str(file_path), "stdout", "--psm", "6"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return result.stdout
        elif ext == ".eml":
            from email import parser
            with open(file_path) as f:
                msg = parser.Parser().parsestr(f.read())
            body = msg.get_body().get_content() if msg.get_body() else ""
            return body
    except Exception as e:
        return f"[EXTRACTION_ERROR: {e}]"
    return "[NO_EXTRACTION_METHOD]"  # placeholder


def run_stage_extract(workspace, verbose=True):
    """Stage 2: Extract + Judge."""
    stage_dir = workspace / "stages" / "02-extract"
    input_file = workspace / "stages" / "01-collect" / "output" / "stage1.jsonl"
    output_file = stage_dir / "output" / "extracted.jsonl"
    flags_dir = stage_dir / "output" / "flags"
    pending_file = stage_dir / "output" / "pending_clarifications.jsonl"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    flags_dir.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()
    if pending_file.exists():
        pending_file.unlink()

    records = load_jsonl(input_file)
    if not records:
        log("No records from Stage 1", verbose)
        return True

    log(f"Extracting {len(records)} invoice(s)...", verbose)

    # Load rules
    vendor_map = load_vendor_rules(workspace / "_config" / "rules" / "vendor_map.csv")
    amount_ranges = load_json(workspace / "_config" / "rules" / "amount_ranges.json")

    extraction_system = (
        "You are an invoice extraction agent. Extract structured data from raw invoice text. "
        "Return ONLY a JSON object with these fields: vendor, amount, tax, date, line_items, "
        "payment_terms, invoice_number, raw_text, confidence_notes. "
        "If any field cannot be determined, use null. Do not guess."
    )

    for rec in records:
        invoice_id = rec["invoice_id"]
        raw_text = rec.get("raw_text", "")

        # Resolve vendor from rules
        vendor_hint = resolve_vendor(raw_text, vendor_map)

        extraction_user = (
            f"Vendor hints from rules: {vendor_hint}\n\n"
            f"Raw invoice text:\n{raw_text[:4000]}"
        )

        try:
            raw = run_llm(extraction_system, extraction_user)
            # Try to parse as JSON
            raw = raw.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip().strip("`")
            extracted = json.loads(raw)
        except Exception as e:
            log(f"  [WARN] Extraction failed for {invoice_id}: {e}", verbose)
            extracted = {
                "vendor": "Miscellaneous - Expenses",
                "amount": 0,
                "tax": None,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "line_items": [],
                "payment_terms": None,
                "invoice_number": None,
                "raw_text": raw_text,
                "confidence_notes": f"EXTRACTION_ERROR: {e}",
            }

        # Judge
        judge_prompt = (
            "Score confidence 0-1 on these three dimensions: VENDOR_RESOLUTION, AMOUNT_ACCURACY, COMPLETENESS. "
            "Return ONLY JSON with fields: vendor_resolution_score, amount_accuracy_score, completeness_score, "
            "overall_confidence, decision (PROCEED|CLARIFY|MISC|FLAG), clarification_question, "
            "clarification_options (array or null), reason."
        )

        try:
            judge = call_judge(judge_prompt, extracted)
        except Exception as e:
            log(f"  [WARN] Judge failed for {invoice_id}: {e}", verbose)
            judge = {
                "overall_confidence": 0.4,
                "decision": "MISC",
                "reason": f"Judge error: {e}",
            }

        # Route
        decision = judge.get("decision", "FLAG")
        score = judge.get("overall_confidence", 0)
        rec["extracted"] = extracted
        rec["judge"] = judge

        if decision == "PROCEED" or score >= THRESHOLD_PROCEED:
            write_jsonl(output_file, [rec])
            log(f"  PROCEED {invoice_id} (score={score:.2f})", verbose)

        elif decision == "CLARIFY" or (score >= THRESHOLD_CLARIFY and score < THRESHOLD_PROCEED):
            question = judge.get("clarification_question", "Is this correct?")
            options = judge.get("clarification_options", ["Yes", "No"])
            rec["clarification"] = {
                "question": question,
                "options": options,
                "retry_count": 0,
                "retry_max": MAX_RETRIES,
            }
            write_jsonl(pending_file, [rec])
            log(f"  CLARIFY {invoice_id}: {question[:60]}", verbose)

        elif score >= THRESHOLD_MISC and score < THRESHOLD_CLARIFY:
            # Default to MISC
            amount = extracted.get("amount", 0)
            misc_vendor = "Miscellaneous - Income" if amount < 0 else "Miscellaneous - Expenses"
            rec["extracted"]["vendor"] = misc_vendor
            rec["misc"] = True
            rec["judge"]["decision"] = "MISC"
            write_jsonl(output_file, [rec])
            # Write flag
            with open(flags_dir / f"misc_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  MISC {invoice_id} (score={score:.2f}, vendor={misc_vendor})", verbose)

        else:
            # FLAG — block
            rec["judge"]["decision"] = "FLAG"
            with open(flags_dir / f"flagged_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  FLAG {invoice_id} (score={score:.2f})", verbose)

        append_audit(stage_dir, {
            "ts": datetime.now().isoformat(),
            "stage": "02-extract",
            "invoice_id": invoice_id,
            "judge_score": score,
            "decision": decision,
            "reason": judge.get("reason", ""),
        })

    log(f"Stage 2 complete. Extracted: {output_file}", verbose)
    return True


def run_stage_categorize(workspace, verbose=True):
    """Stage 3: Categorize + Judge."""
    stage_dir = workspace / "stages" / "03-categorize"
    input_file = workspace / "stages" / "02-extract" / "output" / "extracted.jsonl"
    output_file = stage_dir / "output" / "categorized.jsonl"
    flags_dir = stage_dir / "output" / "flags"
    pending_file = stage_dir / "output" / "pending_clarifications.jsonl"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    flags_dir.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()
    if pending_file.exists():
        pending_file.unlink()

    records = load_jsonl(input_file)
    if not records:
        log("No records from Stage 2", verbose)
        return True

    log(f"Categorizing {len(records)} invoice(s)...", verbose)

    chart = load_json(workspace / "_config" / "rules" / "chart_of_accounts.json")
    vendor_map = load_vendor_rules(workspace / "_config" / "rules" / "vendor_map.csv")
    category_hints = load_json(workspace / "_config" / "rules" / "category_hints.json")

    # Build flat category map
    all_accounts = {v: k for d in chart.values() for k, v in d.items()}

    for rec in records:
        invoice_id = rec["invoice_id"]
        extracted = rec.get("extracted", {})
        vendor = extracted.get("vendor", "Unknown")
        amount = extracted.get("amount", 0)

        # Check for duplicate (simple hash approach)
        is_duplicate = check_duplicate(workspace, vendor, amount, extracted.get("date"))

        # Categorize
        cat_prompt = (
            f"Vendor: {vendor}\nAmount: {amount}\nLine items: {json.dumps(extracted.get('line_items', []))}\n\n"
            f"Chart of accounts: {json.dumps(chart)}\n\n"
            "Determine the correct category. Return JSON with: category, account_code, is_duplicate, "
            "amount_anomaly, anomaly_note, categorization_confidence, rule_applied."
        )

        try:
            raw = run_llm(
                "You are an invoice categorization agent. Return ONLY JSON.",
                cat_prompt
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip().strip("`")
            cat_result = json.loads(raw)
        except Exception as e:
            log(f"  [WARN] Categorization failed for {invoice_id}: {e}", verbose)
            cat_result = {
                "category": "Miscellaneous",
                "account_code": "6999",
                "is_duplicate": False,
                "amount_anomaly": False,
                "anomaly_note": f"Error: {e}",
                "categorization_confidence": "low",
                "rule_applied": None,
            }

        rec["categorized"] = cat_result

        # Judge
        judge_prompt = (
            "Score confidence 0-1: CATEGORY_APPROPRIATENESS, DUPLICATE_DETECTION, ANOMALY_CATCH. "
            "Return ONLY JSON with: overall_confidence, decision, clarification_question, "
            "clarification_options, reason."
        )

        try:
            judge = call_judge(judge_prompt, cat_result)
        except Exception as e:
            judge = {
                "overall_confidence": 0.4,
                "decision": "MISC",
                "reason": f"Judge error: {e}",
            }

        decision = judge.get("decision", "PROCEED")
        score = judge.get("overall_confidence", 0)

        if decision == "PROCEED" or score >= THRESHOLD_PROCEED:
            write_jsonl(output_file, [rec])
            log(f"  PROCEED {invoice_id}: {cat_result.get('category','?')}", verbose)

        elif decision == "CLARIFY" or (score >= THRESHOLD_CLARIFY and score < THRESHOLD_PROCEED):
            question = judge.get("clarification_question", "Is this correct?")
            options = judge.get("clarification_options", ["Yes", "No"])
            rec["clarification"] = {
                "question": question,
                "options": options,
                "retry_count": 0,
                "retry_max": MAX_RETRIES,
            }
            write_jsonl(pending_file, [rec])
            log(f"  CLARIFY {invoice_id}: {question[:60]}", verbose)

        elif score >= THRESHOLD_MISC and score < THRESHOLD_CLARIFY:
            misc_cat = "Miscellaneous - Income" if amount < 0 else "Miscellaneous - Expenses"
            rec["categorized"]["category"] = misc_cat
            rec["categorized"]["account_code"] = "4999" if amount < 0 else "6999"
            rec["misc"] = True
            write_jsonl(output_file, [rec])
            with open(flags_dir / f"misc_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  MISC {invoice_id}", verbose)

        else:
            rec["judge"] = judge
            rec["judge"]["decision"] = "FLAG"
            with open(flags_dir / f"flagged_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  FLAG {invoice_id}", verbose)

        append_audit(stage_dir, {
            "ts": datetime.now().isoformat(),
            "stage": "03-categorize",
            "invoice_id": invoice_id,
            "judge_score": score,
            "decision": decision,
        })

    log(f"Stage 3 complete. Categorized: {output_file}", verbose)
    return True


def run_stage_journal(workspace, verbose=True):
    """Stage 4: Journal Generation + Judge."""
    stage_dir = workspace / "stages" / "04-journal"
    input_file = workspace / "stages" / "03-categorize" / "output" / "categorized.jsonl"
    output_file = stage_dir / "output" / "journal.jsonl"
    flags_dir = stage_dir / "output" / "flags"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    flags_dir.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    records = load_jsonl(input_file)
    if not records:
        log("No records from Stage 3", verbose)
        return True

    log(f"Generating journal entries for {len(records)} invoice(s)...", verbose)

    chart = load_json(workspace / "_config" / "rules" / "chart_of_accounts.json")
    biz_info = load_json(workspace / "_config" / "business_info.json")

    bank_account = biz_info.get("default_bank_account", {"name": "Cash/Bank", "code": "1000"})

    for rec in records:
        invoice_id = rec["invoice_id"]
        extracted = rec.get("extracted", {})
        categorized = rec.get("categorized", {})
        amount = extracted.get("amount", 0)
        vendor = extracted.get("vendor", "Unknown")
        date = extracted.get("date", datetime.now().strftime("%Y-%m-%d"))
        category = categorized.get("category", "Miscellaneous")
        account_code = categorized.get("account_code", "6999")

        # Build journal entries
        is_expense = amount > 0
        if is_expense:
            entries = [
                {"date": date, "account_name": category, "account_code": account_code,
                 "entry_type": "DEBIT", "amount": abs(amount), "memo": vendor},
                {"date": date, "account_name": bank_account["name"], "account_code": bank_account["code"],
                 "entry_type": "CREDIT", "amount": abs(amount), "memo": vendor},
            ]
        else:
            entries = [
                {"date": date, "account_name": bank_account["name"], "account_code": bank_account["code"],
                 "entry_type": "DEBIT", "amount": abs(amount), "memo": vendor},
                {"date": date, "account_name": category, "account_code": account_code,
                 "entry_type": "CREDIT", "amount": abs(amount), "memo": vendor},
            ]

        total_debit = sum(e["amount"] for e in entries if e["entry_type"] == "DEBIT")
        total_credit = sum(e["amount"] for e in entries if e["entry_type"] == "CREDIT")
        is_balanced = abs(total_debit - total_credit) < 0.01

        journal_record = {
            "invoice_id": invoice_id,
            "journal_entries": entries,
            "transaction_total": abs(amount),
            "is_balanced": is_balanced,
            "entry_count": len(entries),
            "confidence_notes": categorized.get("anomaly_note", ""),
        }

        rec["journal"] = journal_record

        # Judge
        judge_prompt = (
            "Score confidence 0-1: BALANCE_ACCURACY, ENTRY_CORRECTNESS, MEMO_QUALITY. "
            "Return ONLY JSON with: overall_confidence, decision, clarification_question, "
            "clarification_options, reason."
        )

        try:
            judge = call_judge(judge_prompt, journal_record)
        except Exception as e:
            judge = {"overall_confidence": 0.4, "decision": "MISC", "reason": str(e)}

        decision = judge.get("decision", "PROCEED")
        score = judge.get("overall_confidence", 0)

        if (decision == "PROCEED" or score >= THRESHOLD_PROCEED) and is_balanced:
            write_jsonl(output_file, [rec])
            log(f"  PROCEED {invoice_id} (balanced={is_balanced})", verbose)

        elif decision == "CLARIFY" or (score >= THRESHOLD_CLARIFY and score < THRESHOLD_PROCEED):
            rec["clarification"] = {
                "question": judge.get("clarification_question", "Is this entry correct?"),
                "options": judge.get("clarification_options", ["Yes", "No"]),
                "retry_count": 0,
                "retry_max": MAX_RETRIES,
            }
            stage_dir / "output" / "pending_clarifications.jsonl"
            with open(stage_dir / "output" / "pending_clarifications.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
            log(f"  CLARIFY {invoice_id}", verbose)

        elif score >= THRESHOLD_MISC:
            # MISC entries — set both accounts to Miscellaneous
            misc_code = "4999" if amount < 0 else "6999"
            misc_entries = [
                {"date": date, "account_name": "Miscellaneous", "account_code": misc_code,
                 "entry_type": "DEBIT", "amount": abs(amount), "memo": "MISC"},
                {"date": date, "account_name": "Miscellaneous", "account_code": misc_code,
                 "entry_type": "CREDIT", "amount": abs(amount), "memo": "MISC"},
            ]
            rec["journal"]["journal_entries"] = misc_entries
            rec["misc"] = True
            write_jsonl(output_file, [rec])
            with open(flags_dir / f"misc_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  MISC {invoice_id}", verbose)

        else:
            rec["judge"] = judge
            rec["judge"]["decision"] = "FLAG"
            with open(flags_dir / f"flagged_{invoice_id}.json", "w") as f:
                json.dump(rec, f, indent=2)
            log(f"  FLAG {invoice_id}", verbose)

        append_audit(stage_dir, {
            "ts": datetime.now().isoformat(),
            "stage": "04-journal",
            "invoice_id": invoice_id,
            "judge_score": score,
            "decision": decision,
        })

    log(f"Stage 4 complete. Journal: {output_file}", verbose)
    return True


def run_stage_export(workspace, verbose=True):
    """Stage 5: Validate + Export."""
    stage_dir = workspace / "stages" / "05-export"
    input_file = workspace / "stages" / "04-journal" / "output" / "journal.jsonl"
    output_dir = stage_dir / "output"

    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(input_file)
    if not records:
        log("No records from Stage 4", verbose)
        # Write empty summary
        with open(output_dir / "export_summary.txt", "w") as f:
            f.write("No journal entries to export.\n")
        return True

    log(f"Exporting {len(records)} journal entry set(s)...", verbose)

    biz_info = load_json(workspace / "_config" / "business_info.json")

    # CSV
    csv_path = output_dir / "journal_export.csv"
    with open(csv_path, "w") as csvf:
        csvf.write("date,account_name,account_code,entry_type,amount,memo,invoice_id\n")
        for rec in records:
            invoice_id = rec["invoice_id"]
            for entry in rec.get("journal", {}).get("journal_entries", []):
                csvf.write(
                    f"{entry['date']},{entry['account_name']},{entry['account_code']},"
                    f"{entry['entry_type']},{entry['amount']:.2f},"
                    f'"{entry["memo"]}",{invoice_id}\n'
                )

    # JSON
    total_debits = 0
    total_credits = 0
    misc_count = 0
    flagged_count = 0

    for rec in records:
        if rec.get("misc"):
            misc_count += 1
        if rec.get("judge", {}).get("decision") == "FLAG":
            flagged_count += 1
        for entry in rec.get("journal", {}).get("journal_entries", []):
            if entry["entry_type"] == "DEBIT":
                total_debits += entry["amount"]
            else:
                total_credits += entry["amount"]

    json_export = {
        "business_name": biz_info.get("business_name", "UNKNOWN"),
        "exported_at": datetime.now().isoformat(),
        "fiscal_year": datetime.now().year,
        "entries": [rec.get("journal", {}) for rec in records],
        "summary": {
            "total_debits": round(total_debits, 2),
            "total_credits": round(total_credits, 2),
            "entry_count": sum(len(r.get("journal", {}).get("journal_entries", [])) for r in records),
            "invoice_count": len(records),
            "misc_count": misc_count,
            "flagged_count": flagged_count,
        },
    }

    with open(output_dir / "journal_export.json", "w") as f:
        json.dump(json_export, f, indent=2)

    # Summary
    summary = (
        f"ICM Bookkeeping — Export Summary\n"
        f"Generated: {datetime.now().isoformat()}\n"
        f"{'─'*50}\n"
        f"Total journal entries: {json_export['summary']['entry_count']}\n"
        f"Total invoices:       {json_export['summary']['invoice_count']}\n"
        f"Total debits:         ${json_export['summary']['total_debits']:.2f}\n"
        f"Total credits:        ${json_export['summary']['total_credits']:.2f}\n"
        f"Balanced:             {'YES' if abs(total_debits - total_credits) < 0.01 else 'NO'}\n\n"
        f"Invoices by status:\n"
        f"  PROCEED:  {len(records) - misc_count - flagged_count}\n"
        f"  MISC:     {misc_count}\n"
        f"  FLAG:     {flagged_count}\n\n"
        f"Export files:\n"
        f"  journal_export.csv  — spreadsheet import\n"
        f"  journal_export.json — API/software import\n"
    )

    with open(output_dir / "export_summary.txt", "w") as f:
        f.write(summary)

    log(summary, verbose)
    log(f"Export complete: {output_dir}", verbose)
    return True


# ── Rule Helpers ───────────────────────────────────────────────────────────────


def load_vendor_rules(csv_path):
    """Load vendor_map.csv into a dict of alias → canonical_name."""
    mapping = {}
    if not csv_path.exists():
        return mapping
    with open(csv_path) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2:
                mapping[parts[0].strip().upper()] = parts[1].strip()
    return mapping


def resolve_vendor(raw_text, vendor_map):
    """Return canonical vendor name if an alias is found in raw_text."""
    upper = raw_text.upper()
    for alias, canonical in vendor_map.items():
        if alias.upper() in upper:
            return canonical
    return None


def load_json(path):
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


# fingerprint-based duplicate detection (simple)
def check_duplicate(workspace, vendor, amount, date, lookback=5):
    fp_file = workspace / "stages" / "03-categorize" / "output" / "fingerprint_index.jsonl"
    if not fp_file.exists():
        return False
    import hashlib
    current_hash = hashlib.md5(f"{vendor}{amount}{date}".encode()).hexdigest()
    lines = fp_file.read_text().strip().split("\n")
    recent = lines[-lookback:] if len(lines) > lookback else lines
    for line in recent:
        try:
            fp = json.loads(line)
            if fp.get("vendor_hash") == current_hash:
                return True
        except:
            pass
    return False


# ── Main ──────────────────────────────────────────────────────────────────────


STAGE_RUNNERS = {
    "01-collect": run_stage_collect,
    "02-extract": run_stage_extract,
    "03-categorize": run_stage_categorize,
    "04-journal": run_stage_journal,
    "05-export": run_stage_export,
}


def main():
    parser = argparse.ArgumentParser(description="ICM Bookkeeping Pipeline Runner")
    parser.add_argument("--workspace", required=True, help="Path to client workspace")
    parser.add_argument("--stages", help="Comma-separated list of stages (default: all)")
    parser.add_argument("--watch", action="store_true", help="Watch input directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.exists():
        print(f"ERROR: Workspace not found: {workspace}")
        sys.exit(1)

    stage_list = args.stages.split(",") if args.stages else STAGES

    log(f"Workspace: {workspace}", args.verbose)
    log(f"Stages: {', '.join(stage_list)}", args.verbose)

    if args.watch:
        log("Watch mode — running on new files...", args.verbose)
        while True:
            result = run_pipeline(workspace, stage_list, args.verbose)
            if not result:
                time.sleep(5)
    else:
        run_pipeline(workspace, stage_list, args.verbose)


def run_pipeline(workspace, stage_list, verbose=True):
    for stage_id in stage_list:
        stage_id = stage_id.strip()
        if stage_id not in STAGE_RUNNERS:
            log(f"Unknown stage: {stage_id}", verbose)
            continue
        log(f"\n=== Running {stage_id} ===", verbose)
        result = STAGE_RUNNERS[stage_id](workspace, verbose)
        if not result:
            log(f"Stage {stage_id} failed. Stopping.", verbose)
            return False
    log("\nPipeline complete.", verbose)
    return True


if __name__ == "__main__":
    main()