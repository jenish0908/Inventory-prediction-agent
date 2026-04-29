import asyncio
import time
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import Product, SalesHistory, Prediction, AgentEvaluation
from app.models.schemas import InventoryDecision
from app.agents.demand_forecasting import run_demand_forecasting_agent
from app.agents.anomaly_detection import run_anomaly_detection_agent
from app.agents.catalog_validation import run_catalog_validation_agent
from app.services.cache import cache_get, cache_set


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    # Gemini 1.5 Flash free tier = $0.00 per token
    # Paid tier rates kept here for reference if you upgrade:
    # input: $0.000000075/token, output: $0.0000003/token
    return 0.0


def _determine_priority(
    restock_recommended: bool,
    anomaly_severity: str,
    current_stock: int,
    reorder_point: int,
    predicted_demand: int,
) -> str:
    if not restock_recommended:
        return "low"

    days_of_stock = current_stock / max(predicted_demand / 7, 1)

    if anomaly_severity == "high" or days_of_stock <= 2:
        return "critical"
    elif anomaly_severity == "medium" or days_of_stock <= 5:
        return "high"
    elif current_stock <= reorder_point:
        return "medium"
    return "low"


def _calculate_restock_quantity(
    predicted_demand_7d: int,
    current_stock: int,
    reorder_point: int,
    lead_time_days: int,
) -> int:
    # Cover lead time + 7-day demand + safety buffer (50% of weekly demand)
    safety_buffer = int(predicted_demand_7d * 0.5)
    lead_time_demand = int((predicted_demand_7d / 7) * lead_time_days)
    needed = (predicted_demand_7d + lead_time_demand + safety_buffer) - current_stock
    return max(needed, reorder_point)


async def run_orchestrator(
    product_id: uuid.UUID,
    db: AsyncSession,
) -> InventoryDecision:
    cache_key = f"prediction:{product_id}"

    cached = await cache_get(cache_key)
    if cached:
        return InventoryDecision(**cached)

    # Fetch product
    result = await db.execute(select(Product).where(Product.id == product_id))
    product: Optional[Product] = result.scalar_one_or_none()
    if product is None:
        raise ValueError(f"Product {product_id} not found")

    # Fetch last 30 days of sales history
    sales_result = await db.execute(
        select(SalesHistory)
        .where(SalesHistory.product_id == product_id)
        .order_by(SalesHistory.sale_date.desc())
        .limit(30)
    )
    sales_rows = sales_result.scalars().all()
    historical_sales = [
        {"sale_date": str(s.sale_date), "units_sold": s.units_sold}
        for s in sales_rows
    ]
    avg_daily_sales = (
        sum(s.units_sold for s in sales_rows) / len(sales_rows) if sales_rows else 0.0
    )

    start_time = time.monotonic()

    # Demand and catalog can run fully in parallel; anomaly needs the demand result first
    (demand_result, demand_in, demand_out), (catalog_result, catalog_in, catalog_out) = (
        await asyncio.gather(
            run_demand_forecasting_agent(
                product_id=str(product_id),
                product_name=product.name,
                category=product.category,
                current_stock=product.current_stock,
                reorder_point=product.reorder_point,
                historical_sales=historical_sales,
            ),
            run_catalog_validation_agent(
                name=product.name,
                category=product.category,
                supplier_id=str(product.supplier_id),
                lead_time_days=product.lead_time_days,
                reorder_point=product.reorder_point,
                current_stock=product.current_stock,
            ),
        )
    )

    anomaly_result, anomaly_in, anomaly_out = await run_anomaly_detection_agent(
        product_name=product.name,
        current_stock=product.current_stock,
        predicted_demand=demand_result.predicted_demand_next_7_days,
        reorder_point=product.reorder_point,
        lead_time_days=product.lead_time_days,
        avg_daily_sales=avg_daily_sales,
    )

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    total_input_tokens = demand_in + anomaly_in + catalog_in
    total_output_tokens = demand_out + anomaly_out + catalog_out
    cost_usd = _estimate_cost(total_input_tokens, total_output_tokens)

    restock_recommended = (
        product.current_stock <= product.reorder_point
        or anomaly_result.anomaly_type == "stockout_risk"
        or anomaly_result.severity == "high"
    )

    restock_quantity = (
        _calculate_restock_quantity(
            demand_result.predicted_demand_next_7_days,
            product.current_stock,
            product.reorder_point,
            product.lead_time_days,
        )
        if restock_recommended
        else 0
    )

    priority_level = _determine_priority(
        restock_recommended,
        anomaly_result.severity,
        product.current_stock,
        product.reorder_point,
        demand_result.predicted_demand_next_7_days,
    )

    reasoning = (
        f"Demand forecast: {demand_result.predicted_demand_next_7_days} units over next 7 days "
        f"(confidence: {demand_result.confidence_score:.0%}, trend: {demand_result.trend_direction}). "
        f"Anomaly: {anomaly_result.anomaly_type} at {anomaly_result.severity} severity. "
        f"Catalog health: {catalog_result.catalog_health_score:.0%}. "
        f"{demand_result.reasoning} {anomaly_result.recommended_action}"
    )

    decision = InventoryDecision(
        product_id=product_id,
        restock_recommended=restock_recommended,
        restock_quantity=restock_quantity,
        priority_level=priority_level,
        reasoning=reasoning,
        demand_forecast=demand_result,
        anomaly_detection=anomaly_result,
        catalog_validation=catalog_result,
        latency_ms=elapsed_ms,
        cost_usd=cost_usd,
    )

    # Generate ID in Python so the evaluation FK is available before flush
    prediction_id_new = uuid.uuid4()
    prediction = Prediction(
        id=prediction_id_new,
        product_id=product_id,
        predicted_demand_7d=demand_result.predicted_demand_next_7_days,
        confidence_score=demand_result.confidence_score,
        restock_recommended=restock_recommended,
        restock_quantity=restock_quantity,
        priority_level=priority_level,
        agent_reasoning=reasoning,
        latency_ms=elapsed_ms,
    )
    db.add(prediction)

    evaluation = AgentEvaluation(
        prediction_id=prediction_id_new,
        hallucination_flag=False,
        cost_usd=cost_usd,
    )
    db.add(evaluation)
    await db.commit()

    # Cache the decision
    await cache_set(cache_key, decision.model_dump(), ttl=300)

    return decision


async def run_orchestrator_batch(
    product_ids: list[uuid.UUID],
    db: AsyncSession,
) -> list[tuple[uuid.UUID, Optional[InventoryDecision], Optional[str]]]:
    """Returns list of (product_id, decision_or_None, error_or_None)."""

    async def safe_run(pid: uuid.UUID):
        try:
            decision = await run_orchestrator(pid, db)
            return pid, decision, None
        except Exception as e:
            return pid, None, str(e)

    results = await asyncio.gather(*[safe_run(pid) for pid in product_ids])
    return list(results)
