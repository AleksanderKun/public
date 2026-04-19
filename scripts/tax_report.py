#!/usr/bin/env python3
"""Entry point for the crypto tax calculator."""

from pathlib import Path

from src.tax.cli import main

if __name__ == "__main__":
    Path(".").resolve()
    raise SystemExit(main())
