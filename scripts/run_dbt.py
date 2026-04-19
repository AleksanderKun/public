#!/usr/bin/env python3
"""Utility script to run dbt commands."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DBT_DIR = PROJECT_ROOT / "dbt"

def run_dbt_command(command: str):
    """Run a dbt command."""
    cmd = ["dbt"] + command.split()
    result = subprocess.run(cmd, cwd=DBT_DIR, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_dbt.py <command>")
        sys.exit(1)
    sys.exit(run_dbt_command(" ".join(sys.argv[1:]))) 