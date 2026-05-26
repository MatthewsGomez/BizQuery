"""
Input model for the analyze_discounts Lambda function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Period parsing helpers
# ---------------------------------------------------------------------------

# Supported formats: "30d", "90d", "180d", "365d" (N days)
_PERIOD_PATTERN = re.compile(r"^(\d+)d$")

# Allowed range for analysis period in days
_MIN_PERIOD_DAYS = 1
_MAX_PERIOD_DAYS = 365


def parse_analysis_period(period: str) -> int:
    """
    Parse an analysis period string and return the number of days.

    Supported format
    ----------------
    * ``"Nd"`` — where N is a positive integer (e.g. ``"30d"``, ``"90d"``)

    Returns
    -------
    int
        Number of days represented by the period string.

    Raises
    ------
    ValueError
        If the string does not match the expected format or the number of
        days is outside the allowed range [1, 365].
    """
    period = period.strip()
    match = _PERIOD_PATTERN.fullmatch(period)
    if not match:
        raise ValueError(
            f"Unrecognized analysis_period format: '{period}'. "
            "Expected format: '<N>d' (e.g. '30d', '90d', '180d')."
        )
    days = int(match.group(1))
    if not (_MIN_PERIOD_DAYS <= days <= _MAX_PERIOD_DAYS):
        raise ValueError(
            f"'analysis_period' must represent between {_MIN_PERIOD_DAYS} and "
            f"{_MAX_PERIOD_DAYS} days, got '{period}' ({days} days)."
        )
    return days


# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnalyzeDiscountsInput:
    """
    Validated input parameters for the analyze_discounts Lambda.

    Parameters
    ----------
    product_id:
        Optional product ID to restrict the analysis to a single product.
    category:
        Optional category name to restrict the analysis to a category.
    analysis_period:
        Optional string representing the number of days to look back for
        sales data when computing rotation metrics.  Must follow the format
        ``"<N>d"`` where N is between 1 and 365 (e.g. ``"30d"``, ``"90d"``).
        Defaults to ``"30d"``.
    """

    product_id: Optional[int] = None
    category: Optional[str] = None
    analysis_period: Optional[str] = "30d"

    def validate(self) -> None:
        """
        Validate the input fields.

        Raises
        ------
        ValueError
            If ``product_id`` is provided but is not a positive integer,
            or if ``analysis_period`` is provided but does not match the
            expected format or is outside the allowed range.
        """
        if self.product_id is not None and self.product_id <= 0:
            raise ValueError(
                f"'product_id' must be a positive integer, got {self.product_id}."
            )
        if self.analysis_period is not None:
            # Delegates format and range validation to parse_analysis_period
            parse_analysis_period(self.analysis_period)

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyzeDiscountsInput":
        """
        Construct an ``AnalyzeDiscountsInput`` from a plain dictionary
        (e.g. from the Lambda event ``parameters`` field).

        Raises
        ------
        ValueError
            If validation fails.
        """
        instance = cls(
            product_id=data.get("product_id"),
            category=data.get("category"),
            analysis_period=data.get("analysis_period", "30d"),
        )
        instance.validate()
        return instance
