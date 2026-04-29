import json
from app.config import settings
from app.models.schemas import DemandForecastResult
from app.services.gemini import groq_client

SYSTEM_PROMPT = """You are a demand forecasting specialist for retail inventory management.
Analyze historical sales data and predict future demand accurately.
Always respond with valid JSON only — no prose, no markdown fences."""

USER_TEMPLATE = """Analyze the following sales history for product "{product_name}" (category: {category}).

Historical sales (last 30 days, newest first):
{sales_data}

Current stock level: {current_stock} units
Reorder point: {reorder_point} units

Return JSON with exactly these fields:
{{
  "predicted_demand_next_7_days": <integer>,
  "confidence_score": <float 0.0-1.0>,
  "trend_direction": <"up" | "down" | "stable">,
  "reasoning": "<2-3 sentence explanation>"
}}"""


async def run_demand_forecasting_agent(
    product_id: str,
    product_name: str,
    category: str,
    current_stock: int,
    reorder_point: int,
    historical_sales: list[dict],
) -> tuple[DemandForecastResult, int, int]:
    """Returns (result, input_tokens, output_tokens)."""

    sales_lines = "\n".join(
        f"  {s['sale_date']}: {s['units_sold']} units" for s in historical_sales
    )

    prompt = USER_TEMPLATE.format(
        product_name=product_name,
        category=category,
        sales_data=sales_lines or "  No historical sales data available.",
        current_stock=current_stock,
        reorder_point=reorder_point,
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

    return DemandForecastResult(
        predicted_demand_next_7_days=int(data["predicted_demand_next_7_days"]),
        confidence_score=float(data["confidence_score"]),
        trend_direction=data["trend_direction"],
        reasoning=data["reasoning"],
    ), input_tokens, output_tokens
