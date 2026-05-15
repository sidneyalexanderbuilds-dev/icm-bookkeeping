#!/usr/bin/env python3
"""
scaffold.py — Workspace Generator for ICM Bookkeeping

Scaffolds a per-client bookkeeping workspace from the template.

Usage:
    python scripts/scaffold.py \
        --template /path/to/icm-bookkeeping \
        --workspace ~/.hermes/workspaces/bookkeeping-acme \
        --client "ACME Corp"
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Scaffold a bookkeeping client workspace")
    parser.add_argument("--template", required=True, help="Path to icm-bookkeeping template")
    parser.add_argument("--workspace", required=True, help="Path for new client workspace")
    parser.add_argument("--client", required=True, help="Client name for labeling")
    args = parser.parse_args()

    template = Path(args.template).resolve()
    workspace = Path(args.workspace).resolve()

    if not template.exists():
        print(f"ERROR: Template not found: {template}")
        return

    print(f"Scaffolding workspace for: {args.client}")
    print(f"Template: {template}")
    print(f"Workspace: {workspace}")

    # Copy template to workspace
    if workspace.exists():
        print(f"Workspace already exists. Adding new files only...")
        for src in template.rglob("*"):
            if src.is_file():
                rel = src.relative_to(template)
                dest = workspace / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
    else:
        shutil.copytree(template, workspace)

    # Update business_info.json with client name
    biz_info_path = workspace / "_config" / "business_info.json"
    if biz_info_path.exists():
        biz_info = json.loads(biz_info_path.read_text())
        biz_info["business_name"] = args.client
        biz_info["workspace_created"] = datetime.now().isoformat()
        biz_info_path.write_text(json.dumps(biz_info, indent=2))
        print(f"Updated business_name: {args.client}")

    print(f"\n✓ Workspace scaffolded: {workspace}")
    print(f"\nNext steps:")
    print(f"  1. Edit {workspace}/_config/business_info.json with your chart of accounts")
    print(f"  2. Add vendor rules to {workspace}/_config/rules/vendor_map.csv")
    print(f"  3. Drop invoices into {workspace}/input/invoices/")
    print(f"  4. Run: python {workspace}/scripts/run_pipeline.py --workspace {workspace} --watch")


if __name__ == "__main__":
    main()