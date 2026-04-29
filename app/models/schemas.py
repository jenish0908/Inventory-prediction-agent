import uuid
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ── Product ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    category: str
    supplier_id: uuid.UUID
    lead_time_days: int
    reorder_point: int
    current_stock: int


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    supplier_id: uuid.UUID
    lead_time_days: int
    reorder_point: int
    current_stock: int
    created_at: datetime


# ── Sub-agent outputs ─────────────────────────────────────────────────────────

class DemandForecastResult(BaseModel):
    predicted_demand_next_7_days: int
    confidence_score: float
    trend_direction: str  # "up" | "down" | "stable"
    reasoning: str


class AnomalyDetectionResult(BaseModel):
    anomaly_type: str  # "stockout_risk" | "overstock_risk" | "unusual_depletion" | "none"
    severity: str       # "low" | "medium" | "high"
    recommended_action: str


class CatalogValidationResult(BaseModel):
    catalog_health_score: float  # 0.0 – 1.0
    missing_fields: list[str]
    validation_warnings: list[str]


# ── Orchestrator output ───────────────────────────────────────────────────────

class InventoryDecision(BaseModel):
    product_id: uuid.UUID
    restock_recommended: bool
    restock_quantity: int
    priority_level: str   # "low" | "medium" | "high" | "critical"
    reasoning: str
    demand_forecast: DemandForecastResult
    anomaly_detection: AnomalyDetectionResult
    catalog_validation: CatalogValidationResult
    latency_ms: int
    cost_usd: float


# ── Batch predict ─────────────────────────────────────────────────────────────

class BatchPredictRequest(BaseModel):
    product_ids: list[uuid.UUID]


class BatchPredictResponse(BaseModel):
    results: list[InventoryDecision]
    total: int
    failed: int


# ── Predictions ───────────────────────────────────────────────────────────────

class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    predicted_demand_7d: int
    confidence_score: float
    restock_recommended: bool
    restock_quantity: int
    priority_level: str
    agent_reasoning: str
    latency_ms: int
    created_at: datetime


# ── Evaluations ───────────────────────────────────────────────────────────────

class EvaluationFeedbackRequest(BaseModel):
    accuracy_score: float
    hallucination_flag: bool
    feedback: str


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prediction_id: uuid.UUID
    accuracy_score: Optional[float]
    hallucination_flag: bool
    cost_usd: Optional[float]
    feedback: Optional[str]
    created_at: datetime


class EvaluationSummary(BaseModel):
    avg_accuracy_score: Optional[float]
    avg_latency_ms: Optional[float]
    avg_cost_usd: Optional[float]
    hallucination_count: int
    hallucination_rate: Optional[float]
    total_predictions: int
    total_evaluations: int


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    redis_connected: bool
    agent_status: str
