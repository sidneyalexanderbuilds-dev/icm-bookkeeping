#!/usr/bin/env python3
"""
handle_clarification.py — Binary Clarification Handler

Reads pending clarifications from a stage's output/pending_clarifications.jsonl,
presents the binary question to the client (via console or webhook),
infers a rule from the answer, writes it to the rules directory,
and retries the stage.

Usage:
    python handle_clarification.py --workspace /path/to/client-workspace --stage 02-extract
    python handle_clarification.py --workspace /path/to/client-workspace --stage 03-categorize
"""

import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

RULES_DIR = "_config/rules"
MAX_RETRIES = 2

# ── Helpers ───────────────────────────────────────────────────────────────────


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


# ── Rule Inference ──────────────────────────────────────────────────────────────


def infer_vendor_rule(question, answer, options, raw_text):
    """
    Given a binary question about vendor identity and the client's answer,
    infer the vendor canonical name and write to vendor_map.csv.
    """
    # Examples of questions we handle:
    # "Is this 'Amazon' or 'Amazon Web Services'?" → answer picks the canonical
    # "Is this 'Amazon' or 'AWS'?" → answer is the canonical
    # "Was this from 'Google' or 'Google Cloud'?" → answer is the canonical

    answer = answer.strip()
    options = [o.strip() for o in options]

    # The answer is the canonical vendor name
    canonical = answer

    # Infer alias from raw_text (find the text that was ambiguous)
    # Look for common patterns in the raw text that could be the alias
    upper = raw_text.upper()
    possible_aliases = []

    for opt in options:
        # Check if option appears in raw text as-is or partially
        if opt.upper() in upper:
            possible_aliases.append(opt)

    # Also try to find other variations
    if "AMZN" in upper or "AMZN" in upper:
        possible_aliases.append("AMZN")
    if "AMAZON" in upper:
        possible_aliases.append("Amazon")
    if "AWS" in upper:
        possible_aliases.append("AWS")
    if "GOOG" in upper:
        possible_aliases.append("GOOG")
    if "GOOGLE" in upper:
        possible_aliases.append("Google")

    return canonical, possible_aliases[:3]  # return canonical + up to 3 aliases


def infer_category_rule(question, answer, options, extracted_vendor):
    """
    Given a binary question about category and the client's answer,
    infer the category and write to category_hints.json.
    """
    answer = answer.strip()

    # The answer is the category name
    category = answer

    return category


def write_vendor_rule(workspace, alias, canonical):
    """Append a vendor rule to vendor_map.csv."""
    rule_file = workspace / RULES_DIR / "vendor_map.csv"
    existing = []
    if rule_file.exists():
        with open(rule_file) as f:
            reader = csv.reader(f)
            existing = [row for row in reader if row]

    # Check if alias already exists
    for row in existing:
        if row[0].upper() == alias.upper():
            # Update canonical
            row[1] = canonical
            with open(rule_file, "w") as f:
                writer = csv.writer(f)
                writer.writerows(existing)
            print(f"Updated vendor rule: {alias} → {canonical}")
            return

    # Append new rule
    with open(rule_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([alias, canonical, ""])  # default_category blank — inferred
    print(f"Added vendor rule: {alias} → {canonical}")


def write_category_hint(workspace, vendor, category):
    """Append a category hint to category_hints.json."""
    hints_file = workspace / RULES_DIR / "category_hints.json"
    hints = {}
    if hints_file.exists():
        with open(hints_file) as f:
            hints = json.load(f)

    if "vendor_categories" not in hints:
        hints["vendor_categories"] = {}

    hints["vendor_categories"][vendor] = category

    with open(hints_file, "w") as f:
        json.dump(hints, f, indent=2)
    print(f"Added category hint: {vendor} → {category}")


# ── Clarification Processing ───────────────────────────────────────────────────


def process_clarification(workspace, stage_id, verbose=True):
    """
    Read pending clarifications, present to client, infer rules, write to rules/.
    """
    stage_dir = workspace / "stages" / stage_id
    pending_file = stage_dir / "output" / "pending_clarifications.jsonl"
    processed_file = stage_dir / "output" / "processed_clarifications.jsonl"

    clarifications = load_jsonl(pending_file)
    if not clarifications:
        print(f"No pending clarifications for {stage_id}")
        return True

    print(f"\nProcessing {len(clarifications)} clarification(s) for {stage_id}...")
    print(f"{'='*60}")

    processed = []

    for rec in clarifications:
        invoice_id = rec.get("invoice_id", "unknown")
        clar = rec.get("clarification", {})
        question = clar.get("question", "Is this correct?")
        options = clar.get("options", ["Yes", "No"])
        retry_count = clar.get("retry_count", 0)
        retry_max = clar.get("retry_max", MAX_RETRIES)

        print(f"\nInvoice: {invoice_id}")
        print(f"Question: {question}")
        print(f"Options: {' | '.join(options)}")

        # Get answer from client (console for now — replace with webhook/telegram)
        answer = None
        while answer is None:
            print(f"\nEnter answer ({'/'.join(options)}): ", end="")
            try:
                raw_answer = input().strip()
                if raw_answer in options:
                    answer = raw_answer
                elif raw_answer.lower() in [o.lower() for o in options]:
                    # Case-insensitive match
                    for o in options:
                        if raw_answer.lower() == o.lower():
                            answer = o
                            break
                else:
                    print(f"Invalid answer. Choose from: {options}")
            except EOFError:
                print("\nNo input available. Run interactively or provide --answer.")
                return False

        print(f"Client answered: {answer}")

        # Infer rule based on question type
        raw_text = rec.get("extracted", {}).get("raw_text", "")
        extracted_vendor = rec.get("extracted", {}).get("vendor", "")
        categorized = rec.get("categorized", {})

        # Route based on stage
        if stage_id == "02-extract":
            # Vendor clarification
            canonical, aliases = infer_vendor_rule(question, answer, options, raw_text)
            for alias in aliases:
                write_vendor_rule(workspace, alias, canonical)
            print(f"→ Vendor rule learned: {aliases} → {canonical}")

        elif stage_id == "03-categorize":
            # Category clarification
            vendor = rec.get("extracted", {}).get("vendor", extracted_vendor)
            category = answer  # answer IS the category
            write_category_hint(workspace, vendor, category)
            # Update the categorized result
            rec["categorized"]["category"] = category
            rec["categorized"]["rule_applied"] = f"clarification:{stage_id}"
            print(f"→ Category rule learned: {vendor} → {category}")

        # Write to audit
        append_audit(stage_dir, {
            "ts": datetime.now().isoformat(),
            "stage": stage_id,
            "invoice_id": invoice_id,
            "action": "clarification_answered",
            "question": question,
            "answer": answer,
            "retry_count": retry_count,
        })

        # Update retry count
        rec["clarification"]["retry_count"] = retry_count + 1
        rec["clarification"]["last_answer"] = answer

        processed.append(rec)

    # Move processed to done
    write_jsonl(processed_file, processed, mode="a")
    pending_file.unlink()  # clear pending

    print(f"\nProcessed {len(processed)} clarification(s). Rules updated.")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Handle binary clarifications")
    parser.add_argument("--workspace", required=True, help="Path to client workspace")
    parser.add_argument("--stage", required=True, help="Stage ID (e.g., 02-extract)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    if not workspace.exists():
        print(f"ERROR: Workspace not found: {workspace}")
        sys.exit(1)

    result = process_clarification(workspace, args.stage, args.verbose)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()