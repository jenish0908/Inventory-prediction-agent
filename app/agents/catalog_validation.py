import json
from app.config import settings
from app.models.schemas import CatalogValidationResult
from app.services.gemini import groq_client

SYSTEM_PROMPT = """You are a product catalog validation specialist for an inventory management system.
Validate product metadata for completeness and reorder feasibility.
Always respond with valid JSON only — no prose, no markdown fences."""

USER_TEMPLATE = """Validate the following product catalog entry:

Product name: {name}
Category: {category}
Supplier ID: {supplier_id}
Lead time (days): {lead_time_days}
Reorder point (units): {reorder_point}
Current stock: {current_stock}

Return JSON with exactly these fields:
{{
  "catalog_health_score": <float 0.0-1.0>,
  "missing_fields": [<list of field names that are null, empty, or invalid>],
  "validation_warnings": [<list of warning strings>]
}}

Scoring guide:
- 1.0: All fields valid and business-logically sound
- 0.7-0.9: Minor issues (unusually long lead time, low reorder point)
- 0.4-0.6: Moderate issues (reorder point higher than current stock)
- 0.0-0.3: Critical issues (missing supplier, zero lead time, negative values)"""


async def run_catalog_validation_agent(
    name: str,
    category: str,
    supplier_id: str,
    lead_time_days: int,
    reorder_point: int,
    current_stock: int,
) -> tuple[CatalogValidationResult, int, int]:
    """Returns (result, input_tokens, output_tokens)."""

    prompt = USER_TEMPLATE.format(
        name=name,
        category=category,
        supplier_id=supplier_id,
        lead_time_days=lead_time_days,
        reorder_point=reorder_point,
        current_stock=current_stock,
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

    return CatalogValidationResult(
        catalog_health_score=float(data["catalog_health_score"]),
        missing_fields=data.get("missing_fields", []),
        validation_warnings=data.get("validation_warnings", []),
    ), input_tokens, output_tokens
