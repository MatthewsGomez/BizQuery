"""
Input model for the query_inventory Lambda function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class QueryInventoryInput:
    """
    Validated input parameters for the query_inventory Lambda.

    Parameters
    ----------
    product_id:
        Optional product ID to look up a specific product's stock.
    sku:
        Optional product SKU to look up a specific product's stock.
    category:
        Optional category name to filter inventory results.
    low_stock_threshold:
        Optional custom threshold for low-stock queries.  When provided,
        products with ``quantity_available <= low_stock_threshold`` are
        considered low-stock instead of using ``min_stock_threshold``.
    """

    product_id: Optional[int] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    low_stock_threshold: Optional[int] = None

    def validate(self) -> None:
        """
        Validate the input fields.

        All fields are optional.  The query is valid even when none of
        ``product_id``, ``sku``, or ``category`` are provided — in that
        case the handler returns all inventory (low-stock + by-category).

        Raises
        ------
        ValueError
            If ``product_id`` is provided but is not a positive integer,
            or if ``low_stock_threshold`` is provided but is negative.
        """
        if self.product_id is not None and self.product_id <= 0:
            raise ValueError(
                f"'product_id' must be a positive integer, got {self.product_id}."
            )
        if self.low_stock_threshold is not None and self.low_stock_threshold < 0:
            raise ValueError(
                f"'low_stock_threshold' must be non-negative, got {self.low_stock_threshold}."
            )

    @classmethod
    def from_dict(cls, data: dict) -> "QueryInventoryInput":
        """
        Construct a ``QueryInventoryInput`` from a plain dictionary (e.g.
        from the Lambda event ``parameters`` field).

        Raises
        ------
        ValueError
            If validation fails.
        """
        instance = cls(
            product_id=data.get("product_id"),
            sku=data.get("sku"),
            category=data.get("category"),
            low_stock_threshold=data.get("low_stock_threshold"),
        )
        instance.validate()
        return instance
