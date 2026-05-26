"""
analyzer.py — Lógica de análisis y recomendaciones de descuentos

Aplica criterios de negocio sobre los datos de rotación de inventario y
descuentos activos para generar recomendaciones priorizadas.

Criterios:
  - days_of_stock > HIGH_DAYS_OF_STOCK y units_sold == 0 → sin historial, excluir
  - days_of_stock > HIGH_DAYS_OF_STOCK → alto stock, baja rotación → HIGH
  - days_of_stock > MEDIUM_DAYS_OF_STOCK → stock moderado → MEDIUM
  - Resto → LOW o sin recomendación

Requisitos: 5.3, 5.4, 5.5
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

HIGH_DAYS_OF_STOCK = 90.0      # > 90 días de stock → alto riesgo
MEDIUM_DAYS_OF_STOCK = 45.0    # > 45 días → riesgo moderado
NO_HISTORY_SENTINEL = 999.0    # valor centinela para productos sin ventas

MIN_DISCOUNT_PCT = 5.0
MAX_DISCOUNT_PCT = 40.0
MIN_PROFIT_MARGIN_PCT = 10.0   # Margen mínimo de ganancia

# MAX_DISCOUNT_PCT respetando el margen mínimo
_ABSOLUTE_MAX_DISCOUNT = 100.0 - MIN_PROFIT_MARGIN_PCT  # 90%


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_recommendations(
    rotation_data: list[dict[str, Any]],
    active_discounts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Genera recomendaciones de descuento basadas en rotación de inventario.

    Args:
        rotation_data:    Lista de dicts con campos del query:
                          id, name, unit_price, category,
                          quantity_available, units_sold, revenue, days_of_stock
        active_discounts: Lista de dicts con campos:
                          product_id, discount_pct, end_date

    Returns:
        Lista de recomendaciones ordenadas por prioridad (HIGH → MEDIUM → LOW).
        Cada recomendación tiene:
          product_id, product_name, sku, category,
          current_stock, days_of_stock_estimated,
          suggested_discount_pct, rationale, priority
    """
    # Index active discounts by product_id for quick lookup
    active_by_product: dict[int, dict] = {
        d["product_id"]: d for d in active_discounts
        if d.get("product_id") is not None
    }

    recommendations: list[dict[str, Any]] = []

    for item in rotation_data:
        product_id = item.get("id")
        product_name = item.get("name", "")
        category = item.get("category", "")
        quantity_available = int(item.get("quantity_available", 0))
        units_sold = int(item.get("units_sold", 0))
        days_of_stock = float(item.get("days_of_stock", 0))

        # Excluir productos sin historial de ventas (sentinel 999)
        if units_sold == 0 or days_of_stock >= NO_HISTORY_SENTINEL:
            continue

        # Determine priority and suggested discount
        priority = None
        suggested_discount_pct = 0.0
        rationale = ""

        if days_of_stock > HIGH_DAYS_OF_STOCK:
            priority = "HIGH"
            # Scale discount with days of stock, capped at MAX_DISCOUNT_PCT
            suggested_discount_pct = min(
                MAX_DISCOUNT_PCT,
                max(MIN_DISCOUNT_PCT, round((days_of_stock / HIGH_DAYS_OF_STOCK - 1.0) * 20, 1))
            )
            rationale = (
                f"Stock elevado ({quantity_available} unidades, "
                f"~{days_of_stock:.0f} días de stock estimados). "
                f"Se recomienda descuento del {suggested_discount_pct:.0f}% para acelerar salida."
            )

        elif days_of_stock > MEDIUM_DAYS_OF_STOCK:
            priority = "MEDIUM"
            suggested_discount_pct = min(
                MAX_DISCOUNT_PCT,
                max(MIN_DISCOUNT_PCT, round((days_of_stock / MEDIUM_DAYS_OF_STOCK - 1.0) * 10, 1))
            )
            rationale = (
                f"Stock moderadamente elevado (~{days_of_stock:.0f} días de stock). "
                f"Descuento del {suggested_discount_pct:.0f}% para mantener rotación."
            )

        if priority is None:
            continue

        # Ensure discount respects minimum profit margin
        suggested_discount_pct = min(suggested_discount_pct, _ABSOLUTE_MAX_DISCOUNT)

        # Check if there's already an equal or better active discount
        existing = active_by_product.get(product_id, {})
        existing_pct = float(existing.get("discount_pct", 0))
        if existing_pct >= suggested_discount_pct:
            continue

        recommendations.append({
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "current_stock": quantity_available,
            "days_of_stock_estimated": round(days_of_stock, 1),
            "suggested_discount_pct": suggested_discount_pct,
            "rationale": rationale,
            "priority": priority,
        })

    # Sort: HIGH first, then MEDIUM, then LOW
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recommendations.sort(key=lambda r: priority_order.get(r["priority"], 99))

    return recommendations


def generate_summary(recommendations: list[dict[str, Any]]) -> str:
    """
    Genera un resumen en lenguaje natural de las recomendaciones.
    """
    if not recommendations:
        return "No se encontraron productos que requieran descuentos en este momento."

    total = len(recommendations)
    high = sum(1 for r in recommendations if r["priority"] == "HIGH")
    medium = sum(1 for r in recommendations if r["priority"] == "MEDIUM")
    low = sum(1 for r in recommendations if r["priority"] == "LOW")

    parts = [f"Se identificaron {total} producto(s) con oportunidades de descuento:"]
    if high:
        parts.append(f"{high} de alta prioridad (alto stock + baja rotación)")
    if medium:
        parts.append(f"{medium} de prioridad media (stock moderado)")
    if low:
        parts.append(f"{low} de baja prioridad")

    return ", ".join(parts[:1]) + " — " + ", ".join(parts[1:]) + "."
