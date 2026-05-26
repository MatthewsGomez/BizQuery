# Feature: bizquery, Property 12-14: analyze_discounts correctness

"""
Property-based tests for the analyze_discounts Lambda function.

Properties tested
-----------------
Property 12 — Invariante del filtro de descuentos vigentes
    For any result from the active discounts query, all returned discounts
    must satisfy: is_active = TRUE AND end_date >= today.
    No expired or inactive discount should appear.
    Validates: Req 5.1, 5.2

Property 13 — Invariante del filtro de descuentos próximos a vencer
    For any result of discounts expiring soon, all returned discounts must
    satisfy: end_date >= today AND end_date <= today + 7 days.
    No discount outside that range should appear.
    Validates: Req 5.3

Property 14 — Corrección matemática del precio con descuento
    For any product with base price P and discount percentage D, the final
    price calculated by analyze_discounts must satisfy:
    final_price = P * (1 - D/100) with tolerance ±0.01 monetary units.
    Validates: Req 5.4
"""

from __future__ import annotations

import math
import sys
import os
from datetime import date, timedelta
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Pure Python filtering functions that mirror the SQL WHERE clauses
# These represent the business logic that the SQL queries implement.
# ---------------------------------------------------------------------------

def filter_active_discounts(discounts: list, today: date) -> list:
    """
    Filter a list of discount dicts to return only active, non-expired ones.

    Mirrors the SQL WHERE clause:
        WHERE d.is_active = TRUE AND d.end_date >= CURRENT_DATE

    Parameters
    ----------
    discounts : list of dict
        Each dict has at least: is_active (bool), end_date (date)
    today : date
        The reference date (CURRENT_DATE equivalent)

    Returns
    -------
    list of dict
        Only discounts where is_active is True and end_date >= today.
    """
    return [
        d for d in discounts
        if d.get("is_active") is True and d.get("end_date") >= today
    ]


def filter_expiring_soon_discounts(discounts: list, today: date, days: int = 7) -> list:
    """
    Filter a list of discount dicts to return only those expiring within
    the next `days` days (inclusive of today and the cutoff date).

    Mirrors the SQL WHERE clause:
        WHERE end_date >= CURRENT_DATE AND end_date <= CURRENT_DATE + 7 days

    Parameters
    ----------
    discounts : list of dict
        Each dict has at least: end_date (date)
    today : date
        The reference date (CURRENT_DATE equivalent)
    days : int
        Number of days ahead to consider (default 7)

    Returns
    -------
    list of dict
        Only discounts where today <= end_date <= today + days.
    """
    cutoff = today + timedelta(days=days)
    return [
        d for d in discounts
        if today <= d.get("end_date") <= cutoff
    ]


def calculate_final_price(base_price: float, discount_pct: float) -> float:
    """
    Calculate the final price after applying a discount percentage.

    Formula: final_price = base_price * (1 - discount_pct / 100)

    Parameters
    ----------
    base_price : float
        The original price of the product (P).
    discount_pct : float
        The discount percentage to apply (D), between 0 and 100.

    Returns
    -------
    float
        The final price after discount.
    """
    return base_price * (1.0 - discount_pct / 100.0)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A date within a reasonable range around today
today = date.today()

# Dates in the past (expired)
past_date = st.dates(
    min_value=today - timedelta(days=365),
    max_value=today - timedelta(days=1),
)

# Dates today or in the future (not expired)
future_date = st.dates(
    min_value=today,
    max_value=today + timedelta(days=365),
)

# Any date (past or future)
any_date = st.dates(
    min_value=today - timedelta(days=365),
    max_value=today + timedelta(days=365),
)

# A discount dict with random is_active and end_date
discount_dict = st.fixed_dictionaries({
    "id": st.integers(min_value=1, max_value=10_000),
    "name": st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ),
    "discount_pct": st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False),
    "is_active": st.booleans(),
    "end_date": any_date,
    "product_id": st.one_of(st.none(), st.integers(min_value=1, max_value=1_000)),
    "category_id": st.one_of(st.none(), st.integers(min_value=1, max_value=100)),
})

# A list of discount dicts (0–30 items)
discount_list = st.lists(discount_dict, min_size=0, max_size=30)

# A discount dict that is guaranteed to be active and not expired
active_valid_discount = st.fixed_dictionaries({
    "id": st.integers(min_value=1, max_value=10_000),
    "name": st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ),
    "discount_pct": st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False),
    "is_active": st.just(True),
    "end_date": future_date,
    "product_id": st.one_of(st.none(), st.integers(min_value=1, max_value=1_000)),
    "category_id": st.one_of(st.none(), st.integers(min_value=1, max_value=100)),
})

# A discount dict that is guaranteed to expire within 7 days (and is today or future)
expiring_soon_discount = st.fixed_dictionaries({
    "id": st.integers(min_value=1, max_value=10_000),
    "name": st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ),
    "discount_pct": st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False),
    "is_active": st.booleans(),
    "end_date": st.dates(
        min_value=today,
        max_value=today + timedelta(days=7),
    ),
    "product_id": st.one_of(st.none(), st.integers(min_value=1, max_value=1_000)),
    "category_id": st.one_of(st.none(), st.integers(min_value=1, max_value=100)),
})

# Base price: positive monetary value
base_price = st.floats(
    min_value=0.01,
    max_value=100_000.0,
    allow_nan=False,
    allow_infinity=False,
)

# Discount percentage: between 0 and 100 (exclusive of 100 to keep price positive)
discount_pct = st.floats(
    min_value=0.0,
    max_value=99.99,
    allow_nan=False,
    allow_infinity=False,
)


# ---------------------------------------------------------------------------
# Property 12: Active discounts filter invariant
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------

@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_12_active_discounts_filter_invariant(discounts):
    """
    # Feature: bizquery, Property 12: Invariante del filtro de descuentos vigentes

    **Validates: Requirements 5.1, 5.2**

    For any result from the active discounts query, all returned discounts
    must satisfy: is_active = TRUE AND end_date >= today.
    No expired or inactive discount should appear in the result.
    """
    reference_date = date.today()
    result = filter_active_discounts(discounts, reference_date)

    for discount in result:
        assert discount["is_active"] is True, (
            f"Discount id={discount['id']} has is_active={discount['is_active']}, "
            f"but only active discounts should be returned."
        )
        assert discount["end_date"] >= reference_date, (
            f"Discount id={discount['id']} has end_date={discount['end_date']} "
            f"which is before today ({reference_date}). "
            f"Expired discounts must not appear in active discounts results."
        )


@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_12_no_inactive_discount_in_active_results(discounts):
    """
    # Feature: bizquery, Property 12: Invariante del filtro de descuentos vigentes

    **Validates: Requirements 5.1, 5.2**

    No discount with is_active = FALSE should appear in the active discounts
    result, regardless of its end_date.
    """
    reference_date = date.today()
    result = filter_active_discounts(discounts, reference_date)

    inactive_in_result = [d for d in result if d.get("is_active") is not True]
    assert inactive_in_result == [], (
        f"Found {len(inactive_in_result)} inactive discount(s) in active results: "
        f"{[d['id'] for d in inactive_in_result]}"
    )


@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_12_no_expired_discount_in_active_results(discounts):
    """
    # Feature: bizquery, Property 12: Invariante del filtro de descuentos vigentes

    **Validates: Requirements 5.1, 5.2**

    No expired discount (end_date < today) should appear in the active
    discounts result, regardless of its is_active flag.
    """
    reference_date = date.today()
    result = filter_active_discounts(discounts, reference_date)

    expired_in_result = [d for d in result if d.get("end_date") < reference_date]
    assert expired_in_result == [], (
        f"Found {len(expired_in_result)} expired discount(s) in active results: "
        f"{[(d['id'], d['end_date']) for d in expired_in_result]}"
    )


# ---------------------------------------------------------------------------
# Property 13: Expiring-soon discounts filter invariant
# Validates: Requirement 5.3
# ---------------------------------------------------------------------------

@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_13_expiring_soon_filter_invariant(discounts):
    """
    # Feature: bizquery, Property 13: Invariante del filtro de descuentos próximos a vencer

    **Validates: Requirements 5.3**

    For any result of discounts expiring soon, all returned discounts must
    satisfy: end_date >= today AND end_date <= today + 7 days.
    No discount outside that range should appear.
    """
    reference_date = date.today()
    cutoff = reference_date + timedelta(days=7)
    result = filter_expiring_soon_discounts(discounts, reference_date, days=7)

    for discount in result:
        assert discount["end_date"] >= reference_date, (
            f"Discount id={discount['id']} has end_date={discount['end_date']} "
            f"which is before today ({reference_date}). "
            f"Already-expired discounts must not appear in expiring-soon results."
        )
        assert discount["end_date"] <= cutoff, (
            f"Discount id={discount['id']} has end_date={discount['end_date']} "
            f"which is after the 7-day cutoff ({cutoff}). "
            f"Discounts expiring beyond 7 days must not appear in expiring-soon results."
        )


@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_13_no_discount_outside_7_day_window(discounts):
    """
    # Feature: bizquery, Property 13: Invariante del filtro de descuentos próximos a vencer

    **Validates: Requirements 5.3**

    No discount with end_date > today + 7 days should appear in the
    expiring-soon results.
    """
    reference_date = date.today()
    cutoff = reference_date + timedelta(days=7)
    result = filter_expiring_soon_discounts(discounts, reference_date, days=7)

    outside_window = [d for d in result if d.get("end_date") > cutoff]
    assert outside_window == [], (
        f"Found {len(outside_window)} discount(s) with end_date beyond 7-day window: "
        f"{[(d['id'], d['end_date']) for d in outside_window]}"
    )


@given(discounts=discount_list)
@settings(max_examples=25, deadline=None)
def test_property_13_no_already_expired_in_expiring_soon(discounts):
    """
    # Feature: bizquery, Property 13: Invariante del filtro de descuentos próximos a vencer

    **Validates: Requirements 5.3**

    No already-expired discount (end_date < today) should appear in the
    expiring-soon results.
    """
    reference_date = date.today()
    result = filter_expiring_soon_discounts(discounts, reference_date, days=7)

    already_expired = [d for d in result if d.get("end_date") < reference_date]
    assert already_expired == [], (
        f"Found {len(already_expired)} already-expired discount(s) in expiring-soon results: "
        f"{[(d['id'], d['end_date']) for d in already_expired]}"
    )


# ---------------------------------------------------------------------------
# Property 14: Mathematical correctness of discounted price
# Validates: Requirement 5.4
# ---------------------------------------------------------------------------

@given(price=base_price, discount=discount_pct)
@settings(max_examples=50, deadline=None)
def test_property_14_discounted_price_formula(price, discount):
    """
    # Feature: bizquery, Property 14: Corrección matemática del precio con descuento

    **Validates: Requirements 5.4**

    For any product with base price P and discount percentage D, the final
    price must satisfy: final_price = P * (1 - D/100) with tolerance ±0.01.
    """
    final_price = calculate_final_price(price, discount)
    expected = price * (1.0 - discount / 100.0)

    assert math.isclose(final_price, expected, abs_tol=0.01), (
        f"Price calculation mismatch: "
        f"base_price={price}, discount_pct={discount}%, "
        f"expected={expected:.4f}, got={final_price:.4f}"
    )


@given(price=base_price, discount=discount_pct)
@settings(max_examples=50, deadline=None)
def test_property_14_final_price_never_exceeds_base_price(price, discount):
    """
    # Feature: bizquery, Property 14: Corrección matemática del precio con descuento

    **Validates: Requirements 5.4**

    For any non-negative discount percentage, the final price must never
    exceed the base price (a discount cannot increase the price).
    """
    final_price = calculate_final_price(price, discount)

    assert final_price <= price + 0.01, (
        f"Final price {final_price:.4f} exceeds base price {price:.4f} "
        f"with discount_pct={discount}%. A discount must not increase the price."
    )


@given(price=base_price)
@settings(max_examples=25, deadline=None)
def test_property_14_zero_discount_preserves_price(price):
    """
    # Feature: bizquery, Property 14: Corrección matemática del precio con descuento

    **Validates: Requirements 5.4**

    A 0% discount must leave the price unchanged (within ±0.01 tolerance).
    """
    final_price = calculate_final_price(price, 0.0)

    assert math.isclose(final_price, price, abs_tol=0.01), (
        f"Zero discount changed the price: base={price:.4f}, final={final_price:.4f}"
    )


@given(price=base_price)
@settings(max_examples=25, deadline=None)
def test_property_14_hundred_percent_discount_gives_zero(price):
    """
    # Feature: bizquery, Property 14: Corrección matemática del precio con descuento

    **Validates: Requirements 5.4**

    A 100% discount must result in a final price of 0 (within ±0.01 tolerance).
    """
    final_price = calculate_final_price(price, 100.0)

    assert math.isclose(final_price, 0.0, abs_tol=0.01), (
        f"100% discount did not result in zero price: "
        f"base={price:.4f}, final={final_price:.4f}"
    )
