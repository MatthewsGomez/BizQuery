"""
Input model and period parsing for the query_sales Lambda function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Period parsing helpers
# ---------------------------------------------------------------------------

def _parse_quarter(year: int, quarter: int) -> tuple[date, date]:
    """Return (start_date, end_date) for a calendar quarter."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"Invalid quarter: Q{quarter}. Must be Q1–Q4.")
    first_month = (quarter - 1) * 3 + 1
    start = date(year, first_month, 1)
    # End of quarter: last day of the third month in the quarter
    last_month = first_month + 2
    # First day of the month after the quarter, minus one day
    if last_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, last_month + 1, 1) - timedelta(days=1)
    return start, end


def _last_day_of_month(year: int, month: int) -> int:
    """Return the last calendar day of the given month."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def parse_period(period: str) -> tuple[date, date]:
    """
    Convert a period string to a (start_date, end_date) tuple.

    Supported formats
    -----------------
    * ``"2025-Q1"``              → first day … last day of Q1 2025
    * ``"2025-01"``              → first … last day of January 2025
    * ``"2025-01-01:2025-03-31"``→ explicit start:end range (inclusive)

    Raises
    ------
    ValueError
        If the string does not match any supported format or contains
        logically invalid values (e.g. end before start).
    """
    period = period.strip()

    # --- Explicit range: "YYYY-MM-DD:YYYY-MM-DD" ---
    range_match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})", period
    )
    if range_match:
        try:
            start = date.fromisoformat(range_match.group(1))
            end = date.fromisoformat(range_match.group(2))
        except ValueError as exc:
            raise ValueError(f"Invalid date in range period '{period}': {exc}") from exc
        if end < start:
            raise ValueError(
                f"End date {end} is before start date {start} in period '{period}'."
            )
        return start, end

    # --- Quarter: "YYYY-QN" ---
    quarter_match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter = int(quarter_match.group(2))
        return _parse_quarter(year, quarter)

    # --- Month: "YYYY-MM" ---
    month_match = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month {month} in period '{period}'.")
        start = date(year, month, 1)
        end = date(year, month, _last_day_of_month(year, month))
        return start, end

    raise ValueError(
        f"Unrecognized period format: '{period}'. "
        "Expected 'YYYY-QN', 'YYYY-MM', or 'YYYY-MM-DD:YYYY-MM-DD'."
    )


# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------

@dataclass
class QuerySalesInput:
    """
    Validated input parameters for the query_sales Lambda.

    Parameters
    ----------
    period:
        Time period for the query. Supported formats: ``"2025-Q1"``,
        ``"2025-01"``, ``"2025-01-01:2025-03-31"``.
    product_id:
        Optional product ID to filter results to a single product.
    category:
        Optional category name to filter results (e.g. ``"Refrigeradores"``).
    compare_period:
        Optional second period for percentage-variation comparison.
        Same format as *period*.
    include_financial:
        When ``True``, the response includes monetary totals
        (``total_amount``, ``final_amount``).  Requires ``owner`` role.
    """

    period: str
    product_id: Optional[int] = None
    category: Optional[str] = None
    compare_period: Optional[str] = None
    include_financial: Optional[bool] = field(default=False)

    def validate(self) -> None:
        """
        Validate the input fields.

        Raises
        ------
        ValueError
            If *period* is missing or empty, or if any period string has an
            unrecognised format.
        """
        if not self.period or not self.period.strip():
            raise ValueError("'period' is required and cannot be empty.")

        # Validate period format (will raise ValueError on bad input)
        parse_period(self.period)

        if self.compare_period is not None and self.compare_period.strip():
            parse_period(self.compare_period)

    @classmethod
    def from_dict(cls, data: dict) -> "QuerySalesInput":
        """
        Construct a ``QuerySalesInput`` from a plain dictionary (e.g. from
        the Lambda event ``parameters`` field).

        Raises
        ------
        ValueError
            If validation fails.
        """
        instance = cls(
            period=data.get("period", ""),
            product_id=data.get("product_id"),
            category=data.get("category"),
            compare_period=data.get("compare_period"),
            include_financial=data.get("include_financial", False),
        )
        instance.validate()
        return instance
