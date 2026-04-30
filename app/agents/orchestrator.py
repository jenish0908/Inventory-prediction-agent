import asyncio
import time
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Prediction, AgentEvaluation
from app.models.schemas import InventoryDecision, SupplierOrderResult
from app.agents.demand_forecasting import run_demand_forecasting_agent
from app.agents.anomaly_detection import run_anomaly_detection_agent
from app.agents.catalog_validation import run_catalog_validation_agent
from app.services.cache import cache_get, cache_set
from app.services.mcp_client import inventory_mcp, supplier_mcp


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
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

    # ── Step 1: Fetch product data + sales history via inventory MCP (parallel) ──
    product_data, sales_data = await asyncio.gather(
        inventory_mcp.get_product_info(str(product_id)),
        inventory_mcp.get_sales_history(str(product_id), days=30),
    )

    if "error" in product_data:
        raise ValueError(product_data["error"])

    historical_sales = sales_data.get("history", [])
    avg_daily_sales = sales_data.get("avg_daily_sales", 0.0)

    start_time = time.monotonic()

    # ── Step 2: LLM agents + supplier lead-time verification (all parallel) ──
    (
        (demand_result, demand_in, demand_out),
        (catalog_result, catalog_in, catalog_out),
        supplier_lead_data,
    ) = await asyncio.gather(
        run_demand_forecasting_agent(
            product_id=str(product_id),
            product_name=product_data["name"],
            category=product_data["category"],
            current_stock=product_data["current_stock"],
            reorder_point=product_data["reorder_point"],
            historical_sales=historical_sales,
        ),
        run_catalog_validation_agent(
            name=product_data["name"],
            category=product_data["category"],
            supplier_id=product_data["supplier_id"],
            lead_time_days=product_data["lead_time_days"],
            reorder_point=product_data["reorder_point"],
            current_stock=product_data["current_stock"],
        ),
        supplier_mcp.get_lead_time(
            supplier_id=product_data["supplier_id"],
            product_category=product_data["category"],
        ),
    )

    # Use supplier-verified lead time; fall back to DB value if MCP returns unexpected data
    verified_lead_time = supplier_lead_data.get(
        "lead_time_days", product_data["lead_time_days"]
    )

    # ── Step 3: Anomaly detection (needs demand result + verified lead time) ──
    anomaly_result, anomaly_in, anomaly_out = await run_anomaly_detection_agent(
        product_name=product_data["name"],
        current_stock=product_data["current_stock"],
        predicted_demand=demand_result.predicted_demand_next_7_days,
        reorder_point=product_data["reorder_point"],
        lead_time_days=verified_lead_time,
        avg_daily_sales=avg_daily_sales,
    )

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    total_input_tokens = demand_in + anomaly_in + catalog_in
    total_output_tokens = demand_out + anomaly_out + catalog_out
    cost_usd = _estimate_cost(total_input_tokens, total_output_tokens)

    restock_recommended = (
        product_data["current_stock"] <= product_data["reorder_point"]
        or anomaly_result.anomaly_type == "stockout_risk"
        or anomaly_result.severity == "high"
    )

    restock_quantity = (
        _calculate_restock_quantity(
            demand_result.predicted_demand_next_7_days,
            product_data["current_stock"],
            product_data["reorder_point"],
            verified_lead_time,
        )
        if restock_recommended
        else 0
    )

    priority_level = _determine_priority(
        restock_recommended,
        anomaly_result.severity,
        product_data["current_stock"],
        product_data["reorder_point"],
        demand_result.predicted_demand_next_7_days,
    )

    reasoning = (
        f"Demand forecast: {demand_result.predicted_demand_next_7_days} units over next 7 days "
        f"(confidence: {demand_result.confidence_score:.0%}, trend: {demand_result.trend_direction}). "
        f"Anomaly: {anomaly_result.anomaly_type} at {anomaly_result.severity} severity. "
        f"Supplier-verified lead time: {verified_lead_time} days "
        f"({supplier_lead_data.get('supplier_name', 'unknown supplier')}). "
        f"Catalog health: {catalog_result.catalog_health_score:.0%}. "
        f"{demand_result.reasoning} {anomaly_result.recommended_action}"
    )

    # ── Step 4: If restocking, create PO + log recommendation via MCP (parallel) ──
    supplier_order: Optional[SupplierOrderResult] = None
    if restock_recommended:
        po_data, _ = await asyncio.gather(
            supplier_mcp.create_purchase_order(
                supplier_id=product_data["supplier_id"],
                product_id=str(product_id),
                product_name=product_data["name"],
                quantity=restock_quantity,
                priority=priority_level,
            ),
            inventory_mcp.log_restock_recommendation(
                product_id=str(product_id),
                quantity=restock_quantity,
                priority=priority_level,
                reason=reasoning,
            ),
        )
        supplier_order = SupplierOrderResult(
            order_id=po_data["order_id"],
            supplier_name=po_data["supplier_name"],
            estimated_delivery_date=po_data["estimated_delivery_date"],
            status=po_data["status"],
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
        supplier_order=supplier_order,
        supplier_lead_time_days=verified_lead_time,
    )

    # ── Step 5: Persist prediction + evaluation to DB ──
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
