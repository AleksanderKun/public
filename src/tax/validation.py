"""
Validation layer for transaction data quality assurance.

Performs checks to identify data quality issues, inconsistencies,
and potential errors before tax calculation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Set

import polars as pl

from .types import ValidationError

logger = logging.getLogger(__name__)


class TransactionValidator:
    """Validates transaction data quality."""

    def __init__(self) -> None:
        """Initialize validator."""
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def _detect_csv_format(self, data_path: Path) -> str:
        """Detect the CSV format based on header contents."""
        with data_path.open("r", encoding="utf-8") as fp:
            first_line = fp.readline().strip().lstrip("\ufeff").upper()

        if first_line.startswith("UID:") or "TIME(UTC)" in first_line:
            return "bybit"
        return "binance"

    def _should_skip_first_row(self, data_path: Path) -> bool:
        """Return True when the first CSV row contains metadata rather than headers."""
        with data_path.open("r", encoding="utf-8") as fp:
            first_line = fp.readline().strip().lstrip("\ufeff")
        return first_line.upper().startswith("UID:")

    def validate_csv(self, data_path: Path) -> Dict[str, int | List[ValidationError]]:
        """
        Perform comprehensive validation on CSV data.

        Checks for:
        - Required columns
        - Data type consistency
        - Duplicate timestamps
        - Missing values
        - Invalid amounts
        - Unknown operations

        Args:
            data_path: Path to transaction CSV.

        Returns:
            Dictionary with validation results.
        """
        logger.info("Starting validation for %s", data_path.name)
        self.errors = []
        self.warnings = []

        if not data_path.exists():
            self.errors.append(
                ValidationError(
                    row_number=0,
                    timestamp=None,
                    message=f"File not found: {data_path}",
                    severity="error",
                )
            )
            return self._get_results()

        file_format = self._detect_csv_format(data_path)
        skip_rows = 1 if self._should_skip_first_row(data_path) else 0

        try:
            frame = pl.read_csv(data_path, try_parse_dates=False, skip_rows=skip_rows)
        except Exception as e:
            self.errors.append(
                ValidationError(
                    row_number=0,
                    timestamp=None,
                    message=f"Failed to read CSV: {e}",
                    severity="error",
                )
            )
            return self._get_results()

        if file_format == "bybit":
            required_cols = ["Uid", "Currency", "Type", "Direction", "Change", "Time(UTC)"]
        else:
            required_cols = ["Czas", "Operacja", "Moneta", "Zmien"]

        missing = [c for c in required_cols if c not in frame.columns]
        if missing:
            self.errors.append(
                ValidationError(
                    row_number=0,
                    timestamp=None,
                    message=f"Missing required columns: {missing}",
                    severity="error",
                )
            )
            return self._get_results()

        # Validate individual rows
        rows = frame.to_dicts()
        timestamps_seen: Set[str] = set()

        for i, row in enumerate(rows, start=2):  # Row 2 because row 1 is header
            self._validate_row(row, i, timestamps_seen, file_format)

        logger.info(
            "Validation complete: %d errors, %d warnings",
            len(self.errors),
            len(self.warnings),
        )

        return self._get_results()

    def _validate_row(
        self, row: Dict, row_number: int, timestamps_seen: Set[str], file_format: str
    ) -> None:
        """Validate a single row."""
        if file_format == "bybit":
            timestamp_str = row.get("Time(UTC)", "")
            operation = " ".join(
                [
                    str(row.get("Type", "") or "").strip(),
                    str(row.get("Direction", "") or "").strip(),
                ]
            ).strip()
            asset = row.get("Currency", "")
            amount_str = row.get("Change", "")
        else:
            timestamp_str = row.get("Czas", "")
            operation = row.get("Operacja", "")
            asset = row.get("Moneta", "")
            amount_str = row.get("Zmien", "")

        # Validate timestamp
        if not timestamp_str:
            self.errors.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=None,
                    message="Missing timestamp",
                    severity="error",
                )
            )
            return

        # Check for duplicates
        if timestamp_str in timestamps_seen:
            self.warnings.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Duplicate timestamp",
                    severity="warning",
                )
            )
        timestamps_seen.add(timestamp_str)

        # Validate operation
        if not operation:
            self.errors.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing operation type",
                    severity="error",
                )
            )

        # Validate asset
        if not asset:
            self.errors.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing asset symbol",
                    severity="error",
                )
            )

        # Validate amount
        if amount_str == "" or amount_str is None:
            self.warnings.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing or empty amount",
                    severity="warning",
                )
            )
        else:
            try:
                amount = float(amount_str)
                if amount == 0.0:
                    self.warnings.append(
                        ValidationError(
                            row_number=row_number,
                            timestamp=timestamp_str,
                            message="Zero amount",
                            severity="warning",
                        )
                    )
            except (ValueError, TypeError):
                self.errors.append(
                    ValidationError(
                        row_number=row_number,
                        timestamp=timestamp_str,
                        message=f"Invalid amount: {amount_str}",
                        severity="error",
                    )
                )

        # Check for duplicates
        if timestamp_str in timestamps_seen:
            self.warnings.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Duplicate timestamp",
                    severity="warning",
                )
            )
        timestamps_seen.add(timestamp_str)

        # Validate operation
        operation = row.get("Operacja", "")
        if not operation:
            self.errors.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing operation type",
                    severity="error",
                )
            )

        # Validate asset
        asset = row.get("Moneta", "")
        if not asset:
            self.errors.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing asset symbol",
                    severity="error",
                )
            )

        # Validate amount
        amount_str = row.get("Zmien", "")
        if amount_str == "" or amount_str is None:
            self.warnings.append(
                ValidationError(
                    row_number=row_number,
                    timestamp=timestamp_str,
                    message="Missing or empty amount",
                    severity="warning",
                )
            )
        else:
            try:
                amount = float(amount_str)
                if amount == 0.0:
                    self.warnings.append(
                        ValidationError(
                            row_number=row_number,
                            timestamp=timestamp_str,
                            message="Zero amount",
                            severity="warning",
                        )
                    )
            except (ValueError, TypeError):
                self.errors.append(
                    ValidationError(
                        row_number=row_number,
                        timestamp=timestamp_str,
                        message=f"Invalid amount: {amount_str}",
                        severity="error",
                    )
                )

    def _get_results(self) -> Dict[str, int | List[ValidationError]]:
        """Get validation results."""
        return {
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "is_valid": len(self.errors) == 0,
        }

    def print_report(self) -> None:
        """Print validation report to logger."""
        logger.info("=" * 60)
        logger.info("VALIDATION REPORT")
        logger.info("=" * 60)

        if not self.errors and not self.warnings:
            logger.info("✓ No issues found")
        else:
            if self.errors:
                logger.error("ERRORS (%d):", len(self.errors))
                for err in self.errors:
                    logger.error(
                        "  Row %d (%s): %s",
                        err.row_number,
                        err.timestamp or "?",
                        err.message,
                    )

            if self.warnings:
                logger.warning("WARNINGS (%d):", len(self.warnings))
                for warn in self.warnings:
                    logger.warning(
                        "  Row %d (%s): %s",
                        warn.row_number,
                        warn.timestamp or "?",
                        warn.message,
                    )

        logger.info("=" * 60)
