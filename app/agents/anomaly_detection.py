import json
from app.config import settings
from app.models.schemas import AnomalyDetectionResult
from app.services.gemini import groq_client

SYSTEM_PROMPT = """You are an inventory anomaly detection specialist.
Analyze stock levels and predicted demand to detect risk conditions.
Always respond with valid JSON only — no prose, no markdown fences."""

USER_TEMPLATE = """Analyze the inventory situation for product "{product_name}":

Current stock level: {current_stock} units
Predicted demand (next 7 days): {predicted_demand} units
Reorder point: {reorder_point} units
Lead time: {lead_time_days} days
Historical daily average: {avg_daily_sales:.1f} units/day

Return JSON with exactly these fields:
{{
  "anomaly_type": <"stockout_risk" | "overstock_risk" | "unusual_depletion" | "none">,
  "severity": <"low" | "medium" | "high">,
  "recommended_action": "<specific action, 1-2 sentences>"
}}

Guidelines:
- stockout_risk: stock will run out before new stock arrives
- overstock_risk: current_stock > 3x predicted_demand
- unusual_depletion: predicted demand > 2x historical daily average * 7
- none: inventory levels are healthy"""


async def run_anomaly_detection_agent(
    product_name: str,
    current_stock: int,
    predicted_demand: int,
    reorder_point: int,
    lead_time_days: int,
    avg_daily_sales: float,
) -> tuple[AnomalyDetectionResult, int, int]:
    """Returns (result, input_tokens, output_tokens)."""

    prompt = USER_TEMPLATE.format(
        product_name=product_name,
        current_stock=current_stock,
        predicted_demand=predicted_demand,
        reorder_point=reorder_point,
        lead_time_days=lead_time_days,
        avg_daily_sales=avg_daily_sales,
    )

    response = await groq_client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    data = json.loads(response.choices[0].message.content)
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    return AnomalyDetectionResult(
        anomaly_type=data["anomaly_type"],
        severity=data["severity"],
        recommended_action=data["recommended_action"],
    ), input_tokens, output_tokens
